# Firebase push notifications

CreditVance sends payment and statement reminders through Firebase Cloud Messaging (project `credvance-cb042`). The mobile app never talks to Firebase Admin. It registers an FCM token with this API, and the server sends the push.

The service-account JSON is a private key. It lives at `secrets/firebase-adminsdk.json`, which git ignores. Do not commit it, paste it into chat, or bake it into a Docker image. The Docker build excludes `secrets/`, and Compose mounts that folder read-only at `/app/secrets`.

## What the server sends

A job runs every day at **09:00 India time** (03:30 UTC). For each signed-in account that has push turned on and at least one device token, it sends a reminder when a wallet card matches the user's offsets.

Defaults:

| Kind | Days before the date | Meaning of `0` |
| :--- | :--- | :--- |
| Payment due | 0, 1, 3 | The due date itself |
| Statement | 0, 1 | Statement day itself |

Product news is off until the user opts in. The daily job does not use that flag.

Each push carries a notification title and body, plus a data payload the app should read when the user taps it:

| Field | Example | Use |
| :--- | :--- | :--- |
| `type` | `due_date`, `statement_date`, `test`, `product`, `admin` | What happened |
| `route` | `/wallet` | Screen to open |
| `user_card_id` | `15` | Wallet card, when this is a reminder |
| `days_until_due` | `0` | Empty string when it does not apply |
| `days_until_statement` | `1` | Empty string when it does not apply |

Android channel id: `creditvance_reminders`. Create that channel before requesting a token, or Android 8+ will drop the notification.

The same reminder is not sent twice on the same UTC date. A token Firebase reports as unregistered is deleted.

## API the app calls

Base path `/api/v1`.

### Register the phone

Call this after a successful login, and again whenever Firebase refreshes the token. Guests can register, but reminders are only sent after the token is tied to an account, so call it again once the user is signed in.

```http
POST /api/v1/notifications/device-token
Authorization: Bearer <access_token>
Content-Type: application/json

{"device_token": "<FCM token>", "platform": "android"}
```

`platform` is `android`, `ios`, or `web`.

### Remove it on logout

```http
DELETE /api/v1/notifications/device-token?device_token=<FCM token>
Authorization: Bearer <access_token>
```

### Preferences

```http
GET /api/v1/notifications/preferences
PATCH /api/v1/notifications/preferences
```

```json
{
  "push_enabled": true,
  "due_reminder_days": [0, 1, 3],
  "statement_reminder_days": [0, 1],
  "product_updates": false
}
```

Send only the fields that changed. An empty day list turns that kind of reminder off. Days are 0 through 31, at most six values.

### Test from a settings button

```http
POST /api/v1/notifications/test
Authorization: Bearer <access_token>
```

Returns `success_count`. If this phone was never registered, the response is 422 and `detail` explains that.

### Inbox

```http
GET /api/v1/notifications/history?limit=20
```

### Server status

```http
GET /api/v1/notifications/status
```

```json
{
  "enabled": true,
  "configured": true,
  "initialized": true,
  "project_id": "credvance-cb042",
  "android_channel_id": "creditvance_reminders"
}
```

`configured: false` means the service-account file is missing on the server. The rest of the API still runs.

### In-app dates, unchanged

`GET /api/v1/notifications/reminders` is still the on-screen list. Push is the same calendar, limited to the offsets above.

## Flutter setup

Use the Firebase **client** config for project `credvance-cb042` (the `google-services` / `GoogleService-Info` files from the Firebase console). The admin JSON in `secrets/` is not a client config and must not ship in the app.

Packages: `firebase_core`, `firebase_messaging`.

1. Initialize Firebase at startup.
2. On Android, create notification channel `creditvance_reminders` with high importance.
3. Ask for notification permission (iOS, and Android 13+).
4. `FirebaseMessaging.instance.getToken()` then `POST /notifications/device-token` with the access token.
5. Subscribe to `onTokenRefresh` and repeat that POST.
6. On logout, `DELETE /notifications/device-token`, then sign out.
7. When a message is opened, read `message.data['route']` and navigate. For reminders the route is `/wallet`.

Background handler (top-level function, registered before `runApp`):

```dart
@pragma('vm:entry-point')
Future<void> firebaseMessagingBackgroundHandler(RemoteMessage message) async {
  await Firebase.initializeApp();
}

void main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await Firebase.initializeApp();
  FirebaseMessaging.onBackgroundMessage(firebaseMessagingBackgroundHandler);
  runApp(const CreditVanceApp());
}
```

Opened from a tap:

```dart
void openFromMessage(RemoteMessage message) {
  final route = message.data['route'];
  if (route == '/wallet') {
    // go to the wallet screen
  } else if (route != null && route.isNotEmpty) {
    // go to that in-app route
  }
}
```

Settings screen:

- Load `GET /notifications/preferences`.
- Save with `PATCH`.
- "Send test notification" calls `POST /notifications/test` and shows `detail` if it fails.

The wallet still needs `statement_day` and `due_day`. A card without those days produces no reminder.

## Operators

Place the JSON at `secrets/firebase-adminsdk.json` (or set `FIREBASE_CREDENTIALS_PATH` to an absolute path).

| Variable | Default | Purpose |
| :--- | :--- | :--- |
| `FIREBASE_ENABLED` | `true` | Turn sending off without removing the file. |
| `FIREBASE_CREDENTIALS_PATH` | `secrets/firebase-adminsdk.json` | Service account. Relative paths start at the repo root. |
| `CRON_PUSH_ENABLED` | `true` | Daily reminder job. |
| `CRON_PUSH_SCHEDULE` | `30 3 * * *` | 09:00 IST. Keep this hour so "today" matches India. |

Apply the schema once:

```bash
alembic upgrade head
```

Revision `a7c3e91b4d20` adds `notification_preferences` and `notification_logs`.

Admin send (not for the app), header `X-Admin-API-Key`:

```http
POST /api/v1/admin/notifications/send
{"title": "New guide", "body": "See how fee waiver works.", "route": "/home"}
```

Without `user_id`, this reaches only accounts with `product_updates: true`. With `user_id`, it reaches that account's devices.

## Checks

`GET /api/v1/notifications/status` should show `project_id` `credvance-cb042` and `configured: true`.

Register a token from a real device, then `POST /notifications/test`. A fake token is stored but Firebase will reject it; that is expected until the Flutter app sends a real FCM token.
