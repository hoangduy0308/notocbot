# Project Brief: NoTocBot

## Executive Summary
NoTocBot là Telegram Bot giúp cá nhân ghi nợ/trả nợ nhanh chóng qua chat tự nhiên, đảm bảo riêng tư và minh bạch.

## Problem Statement
Ghi chép nợ vay nhỏ lẻ thường bị quên hoặc lộn xộn trên Excel/Sổ tay. Cần giải pháp nhanh gọn ngay trên Telegram.

## MVP Scope
* **In-Scope:** Ghi nợ bằng NLP (Regex), Ghi bù trừ (giữ lịch sử), Quản lý danh bạ (Alias, Fuzzy search), Báo cáo số dư, Bảo mật theo Telegram ID.
* **Out-of-Scope:** Đa tiền tệ, OCR hóa đơn, Group Chat, Nhắc nợ tự động.

## Key Decisions
* **Logic:** Ghi bù trừ (Offset Transaction) thay vì xóa nợ.
* **Tech:** Python, PostgreSQL (để không mất data), Render Free Tier.
* **Privacy:** Không dùng PIN, xác thực qua Telegram User ID.