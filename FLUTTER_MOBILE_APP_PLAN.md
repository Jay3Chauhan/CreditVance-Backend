# Flutter Mobile App Master Plan & Architecture Specification
## Credit Card Smart Advisor & Zero-Knowledge Vault (`CardSage`)

> **Note for the Next Conversation**: This document contains the complete context, backend API contracts, Clean Architecture blueprints, state management patterns, and security vault designs needed to build the Flutter mobile application from scratch.

---

## 1. Executive Summary & App Vision

The mobile application (**CardSage**) solves the confusion multi-cardholders experience at checkout:
- **"Which card gives me the highest return/cashback right now?"** (Dining, Swiggy, Flights, Fuel, Grocery).
- **"I need my card number to complete this online checkout."** (Frictionless one-tap copy-paste with biometric authentication).
- **"How many rewards/cashback will I earn on this card compared to market leaders?"** (Interactive offline reward calculator).

### Key Architectural Pillars:
1. **Flutter Clean Architecture + Provider**: Feature-first domain separation with scalable state management (`provider` + `ChangeNotifier`).
2. **Zero-Knowledge Hardware Vault (PCI-DSS & App Store Compliant)**: Full 16-digit PANs and CVVs are stored **strictly on the device's hardware Secure Enclave** (`flutter_secure_storage` + `local_auth` Biometrics). The backend never receives raw card numbers.
3. **Cache-First with Hard Refresh**: Fast sub-second local loading using `hive` / `shared_preferences` with pull-to-refresh (`forceRefresh: true`).
4. **Decoupled Backend**: All network calls connect strictly to our FastAPI backend (`/api/v1/*`), backed by Neon PostgreSQL (731+ cards) and Upstash Redis. Zero direct third-party calls.

---

## 2. Complete Backend API Contracts & Integration Guide

### Base URL Configuration:
- **Android Emulator**: `http://10.0.2.2:8000/api/v1`
- **iOS Simulator**: `http://localhost:8000/api/v1`
- **Physical Device (Local Wi-Fi)**: `http://<YOUR_COMPUTER_LOCAL_IP>:8000/api/v1`
- **Production (Oracle Cloud VM)**: `https://api.yourdomain.com/api/v1`

### Standard Response Envelope:
All API responses follow this consistent JSON envelope:
```json
{
  "success": true,
  "message": "Operation description",
  "data": { ... },
  "meta": {
    "total": 731,
    "page": 1,
    "limit": 20,
    "total_pages": 37,
    "has_next": true,
    "has_prev": false
  },
  "error": null
}
```

---

### Detailed Endpoint Catalog:

#### A. Authentication (`/auth`)
| Method | Endpoint | Description | Headers | Body / Params |
|---|---|---|---|---|
| `POST` | `/auth/register` | Register new account | Content-Type: application/json | `{"email": "user@example.com", "password": "Password123!", "full_name": "Jay"}` |
| `POST` | `/auth/login` | Login & get JWT token | Content-Type: application/json | `{"email": "user@example.com", "password": "Password123!"}` |
| `GET` | `/auth/me` | Fetch user profile | `Authorization: Bearer <TOKEN>` | None |

*Login Response Sample*:
```json
{
  "success": true,
  "data": {
    "access_token": "eyJhbGciOi...",
    "token_type": "bearer",
    "expires_in_minutes": 10080
  }
}
```

---

#### B. Credit Cards Catalog & Details (`/cards`)
| Method | Endpoint | Query Parameters | Description |
|---|---|---|---|
| `GET` | `/cards` | `search`, `bank_slug`, `network`, `fee_type` (`free`,`lt1k`,`1k5k`,`gt5k`), `is_popular`, `sort_by` (`popular`,`return`,`fee_asc`,`fee_desc`,`name`), `page`, `limit` | Paginated cards listing |
| `GET` | `/cards/{slug}` | None | Full card detail with metadata and available tabs list |
| `GET` | `/cards/{slug}/tabs/{tab_name}` | `tab_name`: `earn-categories`, `benefits-and-offers`, `lounge-access`, `milestones`, `redemption-options` | Deep tab perks & rules |

*Card Summary Model (`CardSummary`)*:
```json
{
  "id": 1,
  "slug": "hdfc-infinia-metal",
  "title": "HDFC Infinia Metal Credit Card",
  "display_name": "Infinia Metal",
  "bank_name": "HDFC",
  "bank_slug": "hdfc",
  "bank_logo_url": "https://d3dx7t8uh9asmu.cloudfront.net/bank_square/HDFC.png",
  "web_logo_url": null,
  "card_image_url": "https://d3dx7t8uh9asmu.cloudfront.net/creditcardimages/INFINIA%20METAL%20EDITION.png",
  "joining_fee": 12500.0,
  "renewal_fee": 12500.0,
  "forex_markup_percent": 2.0,
  "return_percentage_raw": "3.3% to 33.3%",
  "return_min_percent": 3.3,
  "return_max_percent": 33.3,
  "network_type": "VISA",
  "lounge_types": ["DOMESTIC_LOUNGE", "INTERNATIONAL_LOUNGE"],
  "benefit_types": ["DINING", "GOLF", "INSURANCE", "CONCIERGE"],
  "is_popular": true,
  "is_currently_issuing": true
}
```

---

#### C. User Wallet Portfolio (`/user-cards`)
> **Security Note**: This endpoint only receives non-sensitive metadata (`card_id`, `nickname`, `last_4_digits`). The 16-digit card number and CVV are stored encrypted locally on the device!

| Method | Endpoint | Headers | Body / Description |
|---|---|---|---|
| `GET` | `/user-cards` | `Authorization: Bearer <TOKEN>` | List cards owned by user |
| `POST` | `/user-cards` | `Authorization: Bearer <TOKEN>` | Add card: `{"card_id": 1, "nickname": "Everyday Infinia", "last_4_digits": "4321", "billing_cycle_day": 15}` |
| `PATCH` | `/user-cards/{id}` | `Authorization: Bearer <TOKEN>` | Update nickname or last 4 digits |
| `DELETE` | `/user-cards/{id}` | `Authorization: Bearer <TOKEN>` | Remove card from user's portfolio |

---

#### D. Smart Advisor ("Which Card Should I Use?") (`/advisor`)
| Method | Endpoint | Headers | Body |
|---|---|---|---|
| `POST` | `/advisor/recommend` | Optional `Authorization: Bearer <TOKEN>` | `{"category_slug": "Dining", "spend_amount": 5000.0, "is_international": false}` |

*Advisor Response Sample*:
```json
{
  "success": true,
  "data": {
    "category_slug": "Dining",
    "spend_amount": 5000.0,
    "top_recommendation": {
      "user_card_id": 12,
      "card_id": 1,
      "card_title": "HDFC Infinia Metal Credit Card",
      "card_slug": "hdfc-infinia-metal",
      "bank_name": "HDFC",
      "card_image_url": "https://d3dx7t8uh9asmu.cloudfront.net/creditcardimages/INFINIA%20METAL%20EDITION.png",
      "nickname": "Everyday Infinia",
      "last_4_digits": "4321",
      "rank": 1,
      "estimated_reward_points": 166.7,
      "estimated_reward_value_inr": 166.70,
      "effective_return_percent": 3.33,
      "reward_type": "points",
      "benefit_highlight": "Accelerated: 25 pts per ₹150 on Dining",
      "notes_or_exclusions": null
    },
    "alternative_cards": [ ... ],
    "market_benchmark_card": { ... },
    "insights": [
      "Use 'Everyday Infinia' for a projected return of ₹166.70 (3.33% effective return)."
    ]
  }
}
```

---

#### E. Reward Calculator (`/calculator`)
| Method | Endpoint | Body |
|---|---|---|
| `POST` | `/calculator/calculate` | `{"card_id": 1, "category_slug": "Dining", "spend_amount": 10000.0}` |

*Calculator Response Sample*:
```json
{
  "success": true,
  "data": {
    "user_card": {
      "card_id": 1,
      "card_name": "Infinia Metal",
      "bank_name": "HDFC",
      "card_image_link": "https://...",
      "reward_points": 333.3,
      "reward_worth": 333.30,
      "is_cashback_card": false,
      "return_percentage": 3.33
    },
    "suggested_card": {
      "card_id": 1,
      "card_name": "Infinia Metal",
      "reward_points": 333.3,
      "reward_worth": 333.30
    },
    "annual_savings": 0.0,
    "suggested_card_is_same": true
  }
}
```

#### F. Taxonomies (`/banks` & `/categories`)
- `GET /banks`: List all 41 banks with logos.
- `GET /categories`: List 16 spend categories (Dining, Flights, Fuel, Grocery, Online Shopping, Rent, Travel, Utilities, etc.).

---

## 3. Flutter Clean Architecture Structure

Organized **feature-first** under `lib/`:

```
lib/
├── core/
│   ├── constants/
│   │   ├── api_endpoints.dart      # Base URL & route constants
│   │   ├── app_colors.dart         # Premium Fintech palette (Dark + Light)
│   │   ├── app_text_styles.dart
│   │   └── app_assets.dart
│   ├── network/
│   │   ├── api_client.dart         # Dio singleton with base options & logging
│   │   ├── auth_interceptor.dart   # Adds Bearer JWT & handles 401 token refresh/logout
│   │   ├── error_handler.dart      # Converts API errors to user-friendly messages
│   │   └── network_info.dart       # connectivity_plus check
│   ├── storage/
│   │   ├── secure_vault_service.dart # Biometrics + flutter_secure_storage (16-digit card vault)
│   │   └── local_cache_service.dart  # Hive / SharedPreferences for catalog cache
│   ├── utils/
│   │   ├── clipboard_helper.dart   # Clipboard copy with 30s auto-clear countdown
│   │   ├── currency_formatter.dart # ₹ Currency formatting (e.g. ₹50,000)
│   │   └── card_formatter.dart     # Masking: •••• •••• •••• 1234
│   └── widgets/
│       ├── custom_button.dart
│       ├── custom_text_field.dart
│       ├── shimmer_card_skeleton.dart
│       └── error_view.dart
├── features/
│   ├── auth/
│   │   ├── data/
│   │   │   ├── models/user_model.dart
│   │   │   └── repositories/auth_repository_impl.dart
│   │   ├── domain/
│   │   │   ├── entities/user_entity.dart
│   │   │   └── repositories/auth_repository.dart
│   │   └── presentation/
│   │       ├── providers/auth_provider.dart
│   │       └── screens/
│   │           ├── login_screen.dart
│   │           └── register_screen.dart
│   ├── advisor/                    # "Which Card Should I Use?"
│   │   ├── data/
│   │   │   ├── models/advisor_model.dart
│   │   │   └── repositories/advisor_repository_impl.dart
│   │   ├── domain/
│   │   │   └── repositories/advisor_repository.dart
│   │   └── presentation/
│   │       ├── providers/advisor_provider.dart
│   │       ├── screens/advisor_screen.dart
│   │       └── widgets/
│   │           ├── category_chip_selector.dart
│   │           ├── recommendation_card.dart
│   │           └── quick_spend_modal.dart
│   ├── wallet/                     # User Wallet & Zero-Knowledge Vault
│   │   ├── data/
│   │   │   ├── models/user_card_model.dart
│   │   │   └── repositories/wallet_repository_impl.dart
│   │   ├── domain/
│   │   │   └── repositories/wallet_repository.dart
│   │   └── presentation/
│   │       ├── providers/wallet_provider.dart
│   │       ├── screens/wallet_screen.dart
│   │       └── widgets/
│   │           ├── credit_card_widget.dart  # Physical credit card UI with copy action
│   │           ├── add_card_modal.dart      # Select card from catalog + optional local vault number
│   │           └── biometric_vault_modal.dart
│   ├── catalog/                    # 731+ Cards Catalog & Explorer
│   │   ├── data/
│   │   │   ├── models/card_model.dart
│   │   │   ├── models/card_tab_model.dart
│   │   │   └── repositories/catalog_repository_impl.dart
│   │   ├── domain/
│   │   │   └── repositories/catalog_repository.dart
│   │   └── presentation/
│   │       ├── providers/catalog_provider.dart
│   │       ├── screens/
│   │           ├── catalog_screen.dart
│   │           └── card_detail_screen.dart
│   │       └── widgets/
│   │           ├── card_grid_item.dart
│   │           ├── filter_bottom_sheet.dart
│   │           └── tab_breakdown_view.dart
│   └── calculator/                 # Reward Calculator
│       ├── data/
│       │   ├── models/calculator_model.dart
│       │   └── repositories/calculator_repository_impl.dart
│       ├── domain/
│       │   └── repositories/calculator_repository.dart
│       └── presentation/
│           ├── providers/calculator_provider.dart
│           ├── screens/calculator_screen.dart
│           └── widgets/comparison_result_card.dart
└── main.dart                       # MultiProvider registration & App Entry
```

---

## 4. State Management with Provider & Hard Refresh Pattern

### Core Provider Principle:
Every provider handles:
1. `ViewState`: `initial`, `loading`, `loaded`, `error`, `refreshing`.
2. Cache-First with `forceRefresh`: Loads cached data from `Hive` immediately, and fetches fresh data in the background or when user pulls to refresh.
3. Pagination & Infinite Scrolling for the 731 cards catalog.

### Sample Pattern: `AdvisorProvider`
```dart
class AdvisorProvider extends ChangeNotifier {
  final AdvisorRepository _repository;
  
  AdvisorProvider(this._repository);

  ViewState _state = ViewState.initial;
  CardRecommendationEntity? _recommendation;
  String? _errorMessage;

  ViewState get state => _state;
  CardRecommendationEntity? get recommendation => _recommendation;
  String? get errorMessage => _errorMessage;

  Future<void> getRecommendation({
    required String categorySlug,
    required double spendAmount,
    bool isInternational = false,
    bool forceRefresh = false,
  }) async {
    _state = ViewState.loading;
    notifyListeners();

    try {
      _recommendation = await _repository.recommend(
        categorySlug: categorySlug,
        spendAmount: spendAmount,
        isInternational: isInternational,
      );
      _state = ViewState.loaded;
    } catch (e) {
      _errorMessage = e.toString();
      _state = ViewState.error;
    }
    notifyListeners();
  }
}
```

---

## 5. Zero-Knowledge Local Card Vault Implementation

### Architecture:
1. **Adding Card**:
   - User picks their card from the catalog (e.g. *HDFC Infinia Metal*).
   - User enters optional nickname (e.g. *"Daily Driver"*) and last 4 digits (e.g. `4321`).
   - User enters their full 16-digit card number and expiry/CVV (optional, for one-tap online checkout).
   - **Backend Call**: Sends ONLY `{"card_id": 1, "nickname": "Daily Driver", "last_4_digits": "4321"}`.
   - **Local Hardware Vault**: Encrypts and saves `{ "pan": "4111...", "cvv": "123", "expiry": "12/28" }` using `FlutterSecureStorage` keyed by `vault_card_${user_card_id}`.
2. **Copying Card Number**:
   - User taps **"Copy Card Number"** on the card widget.
   - App invokes `local_auth` (FaceID / Fingerprint / Device PIN).
   - Upon biometric success, card number is copied to the system clipboard.
   - An in-memory `Timer(Duration(seconds: 30))` automatically flushes the clipboard to empty text, protecting the user.

### Production `SecureCardVaultService` Code:
```dart
import 'dart:async';
import 'package:flutter/services.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:local_auth/local_auth.dart';

class SecureCardVaultService {
  final FlutterSecureStorage _storage;
  final LocalAuthentication _localAuth;
  Timer? _clipboardTimer;

  SecureCardVaultService({
    FlutterSecureStorage? storage,
    LocalAuthentication? localAuth,
  })  : _storage = storage ?? const FlutterSecureStorage(
          aOptions: AndroidOptions(encryptedSharedPreferences: true),
          iOptions: IOSOptions(accessibility: KeychainAccessibility.first_unlock),
        ),
        _localAuth = localAuth ?? LocalAuthentication();

  /// Saves sensitive card data locally (never sent to backend)
  Future<void> saveLocalCardDetails({
    required int userCardId,
    required String cardNumber,
    String? cvv,
    String? expiry,
  }) async {
    await _storage.write(key: 'vault_card_${userCardId}_pan', value: cardNumber);
    if (cvv != null) {
      await _storage.write(key: 'vault_card_${userCardId}_cvv', value: cvv);
    }
    if (expiry != null) {
      await _storage.write(key: 'vault_card_${userCardId}_exp', value: expiry);
    }
  }

  /// Copies card number to clipboard after biometric verification
  Future<bool> copyCardNumberWithBiometrics(int userCardId) async {
    final canAuthenticate = await _localAuth.canCheckBiometrics || await _localAuth.isDeviceSupported();
    if (!canAuthenticate) return false;

    final authenticated = await _localAuth.authenticate(
      localizedReason: 'Authenticate to copy your card number',
      options: const AuthenticationOptions(biometricOnly: false, stickyAuth: true),
    );

    if (authenticated) {
      final pan = await _storage.read(key: 'vault_card_${userCardId}_pan');
      if (pan != null && pan.isNotEmpty) {
        await Clipboard.setData(ClipboardData(text: pan.replaceAll(' ', '')));
        
        // Auto-clear clipboard after 30 seconds for security
        _clipboardTimer?.cancel();
        _clipboardTimer = Timer(const Duration(seconds: 30), () async {
          final current = await Clipboard.getData(Clipboard.kTextPlain);
          if (current?.text == pan.replaceAll(' ', '')) {
            await Clipboard.setData(const ClipboardData(text: ''));
          }
        });
        return true;
      }
    }
    return false;
  }

  Future<void> deleteLocalCardDetails(int userCardId) async {
    await _storage.delete(key: 'vault_card_${userCardId}_pan');
    await _storage.delete(key: 'vault_card_${userCardId}_cvv');
    await _storage.delete(key: 'vault_card_${userCardId}_exp');
  }
}
```

---

## 6. Mobile Application UI / Screen Breakdown

```
[Bottom Navigation Bar]
├── 1. Advisor (Home)  ──▶ "Which card to use?" picker + Instant Top Recommendation
├── 2. Wallet          ──▶ Visual Credit Cards carousel + Copy Number + Add Card
├── 3. Explore (731+)  ──▶ Search, Filters (Bank, Network, Fee), Infinite Scroll
└── 4. Calculator      ──▶ Offline comparison & annual savings simulation
```

### Screen 1: Advisor (Home)
- **Spend Input Header**: Large currency input field (`₹ 5,000`).
- **Category Carousel**: Horizontal chips with icons (*Dining*, *Grocery*, *Flights*, *Fuel*, *Rent*, *Shopping*).
- **International Toggle**: Switch for foreign currency transactions.
- **Hero Recommendation Card**:
  - Gradient background matching card bank color.
  - Card visual graphic, nickname, and bank logo.
  - Return Highlight: *"Earns 166.7 Points worth ₹166.70 (3.3% return)"*.
  - **Action Button**: [Copy Card Number] (Triggers Biometrics & Clipboard).
- **Alternative Cards List**: Ranked cards 2..N with estimated values.

### Screen 2: My Wallet (Vault)
- **Card Carousel**: Realistic credit cards with chip, bank logo, masked number (`•••• •••• •••• 4321`), and nickname.
- **Copy Action Pill**: Tap to copy with biometric feedback.
- **Add Card Floating Button**:
  - Step 1: Select bank & card from searchable 731-card catalog.
  - Step 2: Set nickname & last 4 digits (sent to backend).
  - Step 3 (Optional): Enter full card number & expiry (saved to local secure vault).

### Screen 3: Explore Catalog (731+ Cards)
- **Search Bar**: Debounced instant search by card name, bank, or benefit.
- **Filter Chips**:
  - Bank: HDFC, ICICI, Axis, SBI, Amex...
  - Network: VISA, Mastercard, RuPay, Amex.
  - Fee: Lifetime Free, < ₹1,000, ₹1,000 - ₹5,000, > ₹5,000.
  - Perks: Airport Lounge Access.
- **Card Detail View**:
  - Overview & Best Suited badges.
  - 5 Interactive Tabs:
    1. **Earn Categories**: Base rewards, accelerated categories, exclusions.
    2. **Benefits & Offers**: Dining perks, movie tickets, concierge.
    3. **Lounge Access**: Domestic & international airport lounge network limits.
    4. **Milestones**: Spend milestones and bonus vouchers.
    5. **Redemption Options**: Point conversion rates and catalog.

### Screen 4: Reward Calculator
- **Inputs**:
  - Select Bank (Dropdown or search)
  - Select Card (Filtered by selected bank)
  - Select Spend Category
  - Enter Spend Amount (₹)
- **Results View**:
  - User Card reward points & cash worth.
  - Market Leader benchmark card.
  - Projected Annual Savings Difference (`₹ 12,400 / year`).

---

## 7. Recommended `pubspec.yaml` Dependencies

```yaml
name: card_sage
description: "Credit Card Smart Advisor, Reward Calculator & Local Vault"
publish_to: "none"
version: 1.0.0+1

environment:
  sdk: ">=3.5.0 <4.0.0"

dependencies:
  flutter:
    sdk: flutter

  # State Management & Service Locator
  provider: ^6.1.2

  # Networking & Serialization
  dio: ^5.7.0
  json_annotation: ^4.9.0

  # Local Storage & Security (Zero-Knowledge Vault)
  flutter_secure_storage: ^9.2.2
  local_auth: ^2.3.0
  shared_preferences: ^2.3.2
  hive: ^2.2.3
  hive_flutter: ^1.1.0

  # UI Components & Icons
  cupertino_icons: ^1.0.8
  google_fonts: ^6.2.1
  cached_network_image: ^3.4.1
  flutter_svg: ^2.0.12
  shimmer: ^3.0.0
  intl: ^0.19.0
  flutter_staggered_animations: ^1.1.1

  # Utilities
  connectivity_plus: ^6.0.5

dev_dependencies:
  flutter_test:
    sdk: flutter
  flutter_lints: ^4.0.0
  build_runner: ^2.4.12
  json_serializable: ^6.8.0
```

---

## 8. Implementation Steps for the Next Chat

When you start the new chat for the Flutter app:
1. **Step 1: Project Initialization**: Run `flutter create --org com.cardsage card_sage`, add dependencies, and scaffold the Clean Architecture folder structure.
2. **Step 2: Core Network & Storage Layer**: Implement `ApiClient` (Dio), `AuthInterceptor`, and `SecureCardVaultService`.
3. **Step 3: Authentication Feature**: Build `LoginScreen`, `RegisterScreen`, and `AuthProvider`.
4. **Step 4: Wallet & Secure Vault Feature**: Build `WalletScreen`, `CreditCardWidget`, card addition modal, and biometric copy-paste.
5. **Step 5: Smart Advisor Feature**: Build `AdvisorScreen` with category chips and recommendation engine integration.
6. **Step 6: Explore Catalog & Details**: Build 731-card search, filter bottom sheet, pagination, and the 5-tab detail breakdown.
7. **Step 7: Reward Calculator Feature**: Build offline calculation comparison screen.
8. **Step 8: Polish & Dark Theme**: Apply fintech styling, shimmer skeletons, and error handling.
