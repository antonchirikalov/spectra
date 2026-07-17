---
exemplar:
  id: moigarage-client-platform
  industry: automotive aftersales / auto service
  domain_tags: [auto-service, online-booking, repair-status-tracking, push-notifications, online-payments, 1c-integration]
  project_type: mobile-app
  complexity: medium
  source_types: [brief, notes]
  source_count: 2
  fr_count: 16
  nfr_count: 4
  sections: [domain-grounding, stakeholders, business-context, fr, nfr, business-rules, data-model, integrations, open-questions]
  quality_score: null
  language: en
---

# Requirements: «МойГараж» — Client Mobile App & Service Advisor Portal

Generated: 2026-07-17  
Sources analysed: 2 documents  
Output language: English

> [!NOTE] Both source documents are in Russian. English is confirmed as the intended deliverable language for this requirements document; a Russian-language version can be produced for the «МойГараж» organisation on request. Throughout this document, the term "Client" is reserved for the vehicle-owner role defined in Section 1; the auto service chain itself is referred to as «МойГараж» (see C-002).

## Document Index

| # | File | Type |
|---|------|------|
| 1 | `brief.md` | brief |
| 2 | `notes.txt` | notes |

## Domain Grounding

«МойГараж» is an auto service chain operating 12 branches in Moscow and the Moscow region that today takes all bookings by phone and loses up to 30% of calls in peak season. The project delivers a customer-facing mobile application (iOS and Android from a single codebase) and an internal web portal for service advisors, so that clients can book a service online (choosing branch, service, date, and technician), follow the repair status in real time, receive push notifications, review their vehicle's service history by VIN, and pay online by card or SBP — or on pickup. Service advisors work the incoming order queue through the web portal. The platform must integrate with «МойГараж»'s existing 1C:Управление автосервисом 3.0 system (orders, parts warehouse stock, clients) via its existing web services, and a pilot rollout is constrained to 2 branches over 3 months with personal data stored in the Russian Federation under 152-FZ.

## 1. Stakeholders & Roles

| Role | Description |
|------|-------------|
| Client (vehicle owner) | End user of the mobile app. Registers by phone number, books services online, tracks repair status, views service history by VIN, pays online or on pickup. |
| Service advisor (приёмщик) | Internal staff member of «МойГараж». Works with the order queue through the web portal; primary user of the portal for which the 99.5% availability SLA applies. |
| Technician / master (мастер) | Performs the repair. Clients select a specific technician at booking time. |
| Ops director «МойГараж» | Business-side stakeholder. Articulated the call-centre offload goal, status-visibility pain point, payment choices, and portal SLA in the discovery meeting. |
| Vendor PM | Delivery-side project manager; participant in the discovery meeting of 2026-07-10. |
| 1C contractor | External party holding the documentation for the 1C:Управление автосервисом 3.0 web services; documentation must be obtained from them. |
| Call centre | Affected internal function of «МойГараж»; the online booking channel is intended to reduce its load. |

[Source: `brief.md`, `notes.txt`]

## 2. Business Context

- Network: «МойГараж» operates 12 branches in Moscow and the Moscow region; this is the eventual rollout scope beyond the pilot. [Source: `brief.md`]
- Problem: booking is currently phone-only; in peak season up to 30% of calls are lost. «МойГараж» wants to offload the call centre. [Source: `notes.txt`]
- Problem: clients currently learn their repair status only by calling the service — described by the ops director as a pain point. [Source: `notes.txt`]
- Solution model: a client mobile application plus an internal web portal for service advisors. [Source: `brief.md`]
- Pilot scope: 2 branches over 3 months. [Source: `brief.md`]
- Branch working hours: 8:00–22:00; online booking must nevertheless be available around the clock. [Source: `notes.txt`]
- Payments: card acquiring via Sber; SBP also required, and «МойГараж» (the company) is prepared to absorb the SBP commission rather than pass it on to the vehicle owner. [Source: `notes.txt`]
- Existing system landscape: 1C:Управление автосервисом 3.0 is in use at «МойГараж» and exposes web services; documentation is held by the 1C contractor. [Source: `notes.txt`]
- Compliance: personal data must be stored in the Russian Federation under 152-FZ. [Source: `brief.md`]
- Technology constraint: the mobile app must target iOS and Android from a single codebase. [Source: `brief.md`]

## 3. Functional Requirements

### 3.1 Registration & Client Account

| ID | Requirement | Priority | Source |
|----|-------------|----------|--------|
| FR-001 | The system must register clients by phone number with SMS-code verification. | MUST | `brief.md` |

### 3.2 Online Booking

| ID | Requirement | Priority | Source |
|----|-------------|----------|--------|
| FR-002 | The client must be able to book a service online, choosing branch, service, date, and technician. | MUST | `brief.md` |
| FR-003 | Online booking must be available 24/7, independent of branch working hours (8:00–22:00). | MUST | `notes.txt` |
| FR-004 | The online booking channel must operate as a self-service alternative to phone booking in order to reduce call-centre load, which currently loses up to 30% of calls in peak season. | SHOULD | `notes.txt` |

### 3.3 Repair Status & Notifications

| ID | Requirement | Priority | Source |
|----|-------------|----------|--------|
| FR-005 | The client must see the repair status in real time with the states: accepted / in progress / ready. | MUST | `brief.md`, `notes.txt` |
| FR-006 | The system must send push notifications to the client — at minimum when the vehicle is ready; per the ops director, status-change push notifications are required. | MUST | `brief.md`, `notes.txt` [SCOPE CONFLICT: C-001] |

### 3.4 Service Advisor Web Portal

| ID | Requirement | Priority | Source |
|----|-------------|----------|--------|
| FR-007 | Service advisors must work with the order queue through a web portal. | MUST | `brief.md` |

### 3.5 Vehicle Service History

| ID | Requirement | Priority | Source |
|----|-------------|----------|--------|
| FR-008 | The app must show the vehicle's service history, looked up by VIN. | MUST | `brief.md` |

### 3.6 Payments

| ID | Requirement | Priority | Source |
|----|-------------|----------|--------|
| FR-009 | The system must support online payment by bank card. | MUST | `brief.md`, `notes.txt` |
| FR-010 | The system must support online payment via SBP (Faster Payments System). | MUST | `brief.md`, `notes.txt` |
| FR-011 | Card acquiring must be processed through Sber's internet-acquiring gateway. | MUST | `notes.txt` |
| FR-012 | The client must also be able to pay on vehicle pickup instead of online. | MUST | `brief.md` |

### 3.7 1C Integration

| ID | Requirement | Priority | Source |
|----|-------------|----------|--------|
| FR-013 | The solution must integrate with 1C:Управление автосервисом 3.0 for orders. | MUST | `brief.md`, `notes.txt` |
| FR-014 | The solution must integrate with 1C:Управление автосервисом 3.0 for parts warehouse stock. | MUST | `brief.md` |
| FR-015 | The solution must integrate with 1C:Управление автосервисом 3.0 for clients. | MUST | `brief.md` |
| FR-016 | The 1C integration must use the web services that already exist on «МойГараж»'s 1C:Управление автосервисом 3.0 installation. | MUST | `notes.txt` |

### 3.8 Out of Scope

> [!IMPORTANT] No features were confirmed as excluded by stakeholders in any source document. The two items below are undecided pending stakeholder decision and are tracked as gaps in Section 8.2 (G-002, G-003); until a decision is made, they must not be built into the pilot.

| Feature | Status | Source |
|---------|--------|--------|
| In-app chat with the technician | Undecided pending stakeholder decision — deferred until after the pilot (G-003) | `notes.txt` (ops director: "Нужен ли чат с мастером в приложении? Решить после пилота.") |
| Loyalty / bonus programme | Undecided pending stakeholder decision — pilot scope not confirmed (G-002) | `notes.txt` ("Лояльность/бонусы — в скоупе пилота или нет?") |

## 4. Non-Functional Requirements

| ID | Requirement | Category | Source |
|----|-------------|----------|--------|
| NFR-001 | The service advisor web portal must provide 99.5% availability (SLA). | Availability | `notes.txt` |
| NFR-002 | The advisor portal must not degrade during peak hours, defined as the branch working window 8:00–22:00. Provisional measurable target: p95 interactive response time ≤ 2 seconds at up to 50 concurrent advisor sessions, sustained across the peak window. These targets are provisional, are not stated in any source, and require stakeholder validation (see A-008 and G-011). | Performance | `notes.txt` |
| NFR-003 | All personal data must be stored in the Russian Federation in compliance with Federal Law 152-FZ. | Legal / Compliance | `brief.md` |
| NFR-004 | The mobile application must be delivered for both iOS and Android from a single codebase. | Ops / Maintainability | `brief.md` |

## 5. Business Rules & Constraints

| ID | Rule | Source |
|----|------|--------|
| BR-001 | Client identity is the phone number; registration and verification are performed via SMS code. | `brief.md` |
| BR-002 | The repair status model consists of three states: accepted / in progress / ready. | `brief.md` |
| BR-003 | Online booking operates 24/7 regardless of branch working hours (8:00–22:00). Confirmed stakeholder decision. | `notes.txt` |
| BR-004 | The SBP commission is absorbed by «МойГараж» (the company) and must not be passed on to the client (vehicle owner). Confirmed stakeholder decision. | `notes.txt` |
| BR-005 | The pilot is limited to 2 branches over a 3-month period; the full network of 12 branches is the post-pilot rollout scope. | `brief.md` |

## 6. Data Model (Derived from Sources)

| Entity | Key Attributes (Referenced) | Notes |
|--------|----------------------------|-------|
| Client | phone number (identity), SMS verification status, linked service history, payment method preference (online / on pickup) | [Source: `brief.md`] |
| Vehicle | VIN, service history records | History is looked up by VIN. [Source: `brief.md`] |
| Booking / Order | branch, service, date/time, assigned technician, status (accepted / in progress / ready), payment status | Core entity; also synchronised with 1C. [Source: `brief.md`, `notes.txt`] |
| Branch | working hours (8:00–22:00), membership in the 12-branch network | 2 branches participate in the pilot. [Source: `brief.md`, `notes.txt`] |
| Payment | method (bank card / SBP / on pickup), acquiring provider (Sber), commission handling (SBP commission absorbed by «МойГараж» (the company); must not be passed on to the vehicle owner) | [Source: `brief.md`, `notes.txt`] |
| Parts stock item | warehouse stock, order linkage | Attributes owned by 1C:Управление автосервисом; not detailed in sources. [Source: `brief.md`] |

> [!CAUTION] Technician (master) is referenced as a selectable booking attribute, but no technician profile attributes are described in the sources; the technician data model must be defined during design. [Source: `brief.md`]

## 7. Integration Points

| Integration | Purpose | Priority | Source |
|-------------|---------|----------|--------|
| 1C:Управление автосервисом 3.0 web services | Synchronisation of orders, parts warehouse stock, and clients | MUST | `brief.md`, `notes.txt` |
| Sber internet acquiring (payment gateway) | Online card payments | MUST | `notes.txt` |
| SBP (Faster Payments System, NSPK) via acquiring bank | QR-based online payments with instant settlement; commission absorbed by «МойГараж» (the company); must not be passed on to the vehicle owner | MUST | `brief.md`, `notes.txt` |
| SMS / OTP provider (not yet selected) | Delivery of SMS verification codes for phone-number registration | MUST | `brief.md` (implied) |
| Apple Push Notification service (APNs) + Firebase Cloud Messaging (FCM) | Push delivery to iOS and Android clients | MUST | `brief.md`, `notes.txt` (implied by push requirement and iOS/Android targets) |

Enrichment notes (external research, 2026-07-17):

> [!NOTE] 1C platform web services are natively published as SOAP (WS) or HTTP/REST endpoints with JSON/XML payloads; the notes confirm web services already exist on «МойГараж»'s installation, and their documentation is held by the 1C contractor (see G-001). Exact endpoint style, authentication, and throttling limits must be confirmed against that documentation before integration design.

> [!NOTE] Sber's internet-acquiring gateway exposes a documented REST API based on a registered-order model with server-to-server callback notifications and merchant-credential authentication (official developer documentation at developers.sber.ru and the payment-gateway API reference).

> [!NOTE] SBP merchant integration is performed through a partner bank's REST API using URL-based dynamic QR codes; funds settle to the merchant account instantly, and commission is materially lower than card acquiring — consistent with «МойГараж»'s decision to absorb the SBP commission (BR-004).

## 8. Open Questions, Conflicts & Assumptions

### 8.1 Conflicts Found

| # | Conflict | Documents in Conflict | Resolution |
|---|----------|-----------------------|------------|
| C-001 | Push-notification trigger scope. The brief specifies push notifications when the vehicle is ready ("Push-уведомления о готовности автомобиля"). The meeting notes, quoting the ops director, require push notifications about repair status generally ("Статус ремонта клиенты узнают звонком — это больная тема, нужны push и онлайн-статус"). | `brief.md` vs. `notes.txt` | Proposed resolution: implement push notifications on every repair-status transition (accepted / in progress / ready), with the readiness notification as the guaranteed minimum. Rationale: the notes are the more recent, direct stakeholder statement and frame status visibility as the core pain point. Confirm at pilot kickoff. |
| C-002 | Terminology ambiguity for the SBP commission decision. The notes record the decision as "Комиссию по СБП клиент готов взять на себя", where "клиент" denotes the «МойГараж» organisation (the vendor's client), not the vehicle owner. Read against this document's glossary (Section 1), the phrase "absorbed by client" would reverse the decision. | `notes.txt` (internal terminology) vs. Section 1 glossary of this document | RESOLVED. Per BR-004, the SBP commission is absorbed by «МойГараж» (the company) and must not be passed on to the client (vehicle owner). In this document the term "Client" is reserved for the vehicle-owner role; the company is always referred to as «МойГараж». |

### 8.2 Gaps (Information Not Found in Any Source Document)

| # | Gap | Impact |
|---|-----|--------|
| G-001 | The 1C web-services documentation is held by the 1C contractor and has not been obtained. Endpoint style (SOAP vs REST), authentication, and payload formats are therefore unknown. | Blocks 1C integration design (FR-013–FR-016) and integration estimation |
| G-002 | Loyalty / bonus programme: is it inside the pilot scope or not? | Pilot scope definition, data model, development effort |
| G-003 | In-app chat with the technician: stakeholder deferred the decision until after the pilot. | Post-pilot roadmap; notification and messaging architecture if approved |
| G-004 | "Real time" for repair status (FR-005) has no quantitative latency target in any source (seconds vs minutes; push vs polling; source of status events — advisor portal, 1C, or both). | Architecture of the status-update pipeline, NFR definition, testability |
| G-005 | SMS provider for registration codes is not selected; per-message cost, delivery SLA, and sender-name registration are unknown. | FR-001 delivery reliability, operating cost, vendor selection |
| G-006 | Booking slot model is undefined: source of available slots (1C schedule vs a new capacity engine), slot granularity, and overbooking handling. | FR-002 design; determines depth of 1C integration |
| G-007 | Payment-on-pickup flow is not described (terminal vs cash, receipt issuance, fiscalisation/54-FZ cash-receipt handling). | FR-012 implementation; potential fiscal-compliance integration |
| G-008 | App distribution channels are not specified (App Store, Google Play, RuStore). | Release planning for the Russian market; RuStore may be required |
| G-009 | Pilot success criteria / KPIs are not defined (e.g., target share of bookings made online, call-volume reduction target against the 30% seasonal loss baseline). | Pilot go/no-go evaluation after 3 months |
| G-010 | Push-delivery strategy for the Russian market (APNs + FCM vs RuStore Push / local fallback) is not addressed in any source. | Notification reliability for Android devices in RU |
| G-011 | Peak-hours performance targets for the advisor portal are undefined in all sources: no baseline response time, no concurrency figure, and no quantitative degradation ceiling exist (the notes state only "деградация в час пик недопустима"). Provisional targets are proposed in NFR-002 and recorded as assumption A-008. | Testability of NFR-002; load-test design and portal infrastructure sizing |

### 8.3 Explicit Assumptions

> Assumptions are marked clearly and have NOT been confirmed by source documents. They require validation with the client.

| # | Assumption | Basis |
|---|------------|-------|
| A-001 | The mobile app UI language is Russian only; no localisation is required. | All sources are in Russian; the market is Moscow and Moscow region. |
| A-002 | A client account may register multiple vehicles, with service history maintained per VIN. | FR-008 requires history lookup by VIN, implying vehicle-centric records under one client. |
| A-003 | The advisor portal is a browser-based web application; no native desktop client is required. | The brief specifies "веб-портал" (web portal). |
| A-004 | The single-codebase constraint will be met with a cross-platform framework (e.g., Flutter or React Native); the specific framework is not yet selected. | Brief constraint "iOS и Android из одной кодовой базы" without naming a technology. |
| A-005 | 1C:Управление автосервисом 3.0 remains the system of record for orders, parts stock, and clients during the pilot; the new platform reads and writes through its existing web services rather than replacing them. | Notes confirm the 1C installation and existing web services; sources require integration, not migration. |
| A-006 | Repair-status change events originate from the advisor portal and/or 1C and are propagated to the client app. | Advisors manage the order queue (`brief.md`); 1C holds orders (`brief.md`, `notes.txt`). |
| A-007 | Push notifications are the primary channel for status and readiness alerts; no SMS fallback for status notifications is required. | Sources mention push only (`brief.md`, `notes.txt`); SMS appears only for registration codes. |
| A-008 | Peak-hours performance targets for the advisor portal (NFR-002) are provisionally set at p95 interactive response time ≤ 2 seconds with up to 50 concurrent advisor sessions, with the peak window defined as branch working hours 8:00–22:00. | The notes require "деградация в час пик недопустима" (SRC-NOT-008) without quantification; the 50-session figure assumes roughly 4 concurrent advisors per branch across the 12-branch network, providing headroom beyond the 2-branch pilot. Requires stakeholder validation (see G-011). |

---

*End of requirements document.*
