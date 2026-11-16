# 39 dòng tiêu đề bị bỏ khi parse lại 141 báo cáo

Tất cả dòng dưới đây có `raw_current=''`, `raw_prior=''`, nhãn kết thúc bằng `:`; không dòng nào có giá trị số bị bỏ. `code` đều null. Bản parse ứng viên so với JSON đang dùng có 39 dòng mất, 0 dòng thêm, 0 tài liệu đổi `content_hash` chunk. Bốn báo cáo FPT đã được parse lại ở lượt trước, nên các dòng tiêu đề FPT không nằm trong phép so 39 dòng này.

| Tài liệu | Nhãn | Loại báo cáo |
|---|---|---|
| BSR_2022_Hopnhat, BSR_2023_Hopnhat, BSR_2024_Hopnhat, BSR_2025_Hopnhat | Điều chỉnh/Điều chính cho các khoản: | CASH_FLOW |
| DCM_2022_Hopnhat, DCM_2023_Hopnhat, DCM_2024_Hopnhat, DCM_2025_Hopnhat | Điều chỉnh cho các khoản: | CASH_FLOW |
| DHG_2022_Hopnhat, DHG_2023_Chung, DHG_2025_Chung | Điều chỉnh/Điều chính cho các khoản: | CASH_FLOW |
| GEE_2022_Hopnhat, GEE_2025_Hopnhat | Điều chỉnh cho các khoản: | CASH_FLOW |
| GEX_2022_Hopnhat, GEX_2023_Hopnhat, GEX_2025_Hopnhat | Điều chỉnh/Điều chính cho các khoản: | CASH_FLOW |
| GMD_2023_Hopnhat, GMD_2025_Hopnhat | 2. Điều chỉnh cho các khoản: | CASH_FLOW |
| HAH_2025_Hopnhat | Điều chính cho các khoản: | CASH_FLOW |
| HUT_2022_Hopnhat, HUT_2024_Hopnhat, HUT_2025_Hopnhat | Điều chỉnh cho các khoản: | CASH_FLOW |
| OIL_2022_Hopnhat, OIL_2023_Hopnhat, OIL_2024_Hopnhat, OIL_2025_Hopnhat | Điều chỉnh cho các khoản: | CASH_FLOW |
| PET_2023_Hopnhat | Trong đó: | BALANCE_SHEET |
| PVI_2022_Hopnhat, PVI_2023_Hopnhat | Điều chỉnh cho các khoản: | CASH_FLOW |
| PVT_2022_Hopnhat, PVT_2023_Hopnhat, PVT_2024_Hopnhat, PVT_2025_Hopnhat | Điều chỉnh cho các khoản: | CASH_FLOW |
| SSH_2022_Hopnhat, SSH_2023_Hopnhat, SSH_2024_Hopnhat, SSH_2025_Hopnhat | Điều chỉnh/Điều chính cho các khoản: | CASH_FLOW |
| VCR_2023_Chung | Điều chỉnh cho các khoản: | CASH_FLOW |
| VRE_2024_Hopnhat | Điều chỉnh cho các khoản: | CASH_FLOW |
