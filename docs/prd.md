# Product Requirements Document (PRD) - NoTocBot

**Version:** 1.0
**Status:** Approved
**Author:** John (PM)

## 1. Goals & Background Context

### Goals
* **Tốc độ & Tiện lợi:** Người dùng có thể ghi lại một khoản nợ mới trong vòng dưới 10 giây thông qua giao diện chat tự nhiên (NLP).
* **Bảo mật & Riêng tư:** Đảm bảo dữ liệu tài chính cá nhân được bảo vệ, dựa trên xác thực Telegram ID.
* **Minh bạch dữ liệu:** Duy trì lịch sử giao dịch chính xác thông qua cơ chế ghi bù trừ (offset), không xóa dữ liệu cũ.
* **Độ ổn định & Chi phí:** Hệ thống backend hoạt động ổn định trên hạ tầng miễn phí (Render + PostgreSQL), không mất mát dữ liệu.

### Background Context
Việc quản lý các khoản vay mượn nhỏ lẻ cá nhân thường bị lãng quên hoặc ghi chép thiếu hệ thống. NoTocBot giải quyết vấn đề này bằng cách tích hợp vào Telegram, cung cấp một "trợ lý ghi nợ" ngay trong luồng chat với cú pháp tự nhiên, giúp người dùng quản lý tài chính cá nhân với bạn bè chính xác và nhanh chóng.

## 2. Requirements

### 2.1 Functional Requirements (Chức năng)
* **FR1 - Ghi nợ thông minh (NLP Basic):** Bot phân tích tin nhắn văn bản tự nhiên để trích xuất: *Tên người nợ*, *Số tiền*, *Lý do*.
    * *Input:* "Tuấn nợ 50k tiền cơm" -> *Output:* Ghi nợ cho Tuấn 50.000đ.
* **FR2 - Ghi trả nợ (Ghi bù trừ):** Hỗ trợ cú pháp ghi nhận trả nợ. Hệ thống tạo giao dịch mới (Offset Transaction) loại `CREDIT`, không xóa giao dịch cũ để giữ lịch sử.
* **FR3 - Xác thực người dùng:** Tự động nhận diện qua `Telegram User ID`. Dữ liệu của người dùng A hoàn toàn tách biệt với người dùng B.
* **FR4 - Quản lý danh bạ thông minh:** Tự động tạo hồ sơ người nợ mới. Nếu tên nhập vào gần giống tên có sẵn (Fuzzy Search), Bot sẽ hỏi lại để xác nhận (tránh ghi nhầm).
* **FR5 - Báo cáo số dư:** Xem tổng số tiền một người đang nợ (Tổng Nợ - Tổng Trả).
* **FR6 - Tra cứu lịch sử:** Xem 5-10 giao dịch gần nhất với một người.
* **FR7 - Hướng dẫn:** Lệnh `/help` hiển thị hướng dẫn sử dụng.
* **FR8 - Quản lý Biệt danh (Alias):** Cho phép gán nhiều tên gọi tắt cho một người (ví dụ: gán "Béo" = "Tuấn Anh").

### 2.2 Non-Functional Requirements (Phi chức năng)
* **NFR1 - Performance:** Phản hồi dưới 2 giây.
* **NFR2 - Data Integrity:** Sử dụng Database quan hệ (PostgreSQL) để đảm bảo an toàn dữ liệu tài chính.
* **NFR3 - Scalability:** Thiết kế Database sẵn sàng cho tính năng Group Chat trong tương lai (có trường `group_id`).
* **NFR4 - Cost Efficiency:** Tối ưu để chạy trên Free Tier (Render, 512MB RAM).

## 3. Technical Assumptions
* **Language:** Python 3.11+
* **Framework:** `python-telegram-bot` (v20+)
* **Database:** PostgreSQL (Sử dụng dịch vụ cloud như Supabase/Neon/Render Postgres).
* **Hosting:** Render.com (Web Service - Webhook Mode).
* **Architecture:** Monolithic Layered Architecture.

## 4. Epic List

### Epic 1: Foundation & Core Operations
Xây dựng nền tảng, kết nối Database và các lệnh cơ bản (`/start`, ghi nợ thủ công).

### Epic 2: Intelligence & Contact Management
Tích hợp NLP Parser, xử lý tìm kiếm tên thông minh (Fuzzy Search) và quản lý Alias.

### Epic 3: Reporting & Insight
Tính toán số dư ròng (Net Balance), lịch sử giao dịch, bảo mật dữ liệu và Deploy production.

## 5. User Stories (Core)

* **Story 1.1:** Project Setup & Hello World (Init repo, Docker, Bot Token).
* **Story 1.2:** Database Schema & Connection (Users, Transactions tables).
* **Story 1.3:** Manual Debt Recording (Lệnh `/add` cứng).
* **Story 1.4:** Manual Repayment Recording (Lệnh `/paid` cứng).
* **Story 2.1:** Basic NLP Parser (Regex xử lý chat tự nhiên).
* **Story 2.2:** Smart Contact Matching (Logic hỏi lại khi tên gần giống).
* **Story 2.3:** Alias Management (Lệnh `/alias`).
* **Story 3.1:** Calculate Net Balance (Logic tính tổng).
* **Story 3.2:** Transaction History (Logic truy vấn log).
* **Story 3.3:** Security Scope (Middleware check User ID).