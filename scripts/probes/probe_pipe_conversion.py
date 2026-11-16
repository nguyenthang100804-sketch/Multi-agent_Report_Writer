import re

def test_conversion():
    lines = [
        "CHỈ TIÊU | Mã số | Năm 2025 VND | Năm 2024 VND",
        "I. Lưu chuyển tiền từ hoạt động kinh doanh",
        "1. Lợi nhuận trước thuế 01 2.212.403.247.115 2.645.190.487.574",
        "2. Điều chỉnh cho các khoản",
        "- Khâu hao Tài sản cố định và phân bổ tiền thuê đất 02 460.196.425.458 443.728.016.028",
        "- Các khoản dự phòng 03 (1.737.699.666) 3.327.627.630",
        "- Lưu chuyển tiền thuần từ hoạt động kinh doanh 20 2.106.348.502.955 2.032.605.724.809",
        "Lưu chuyển tiền thuần trong kỳ 50 (266.258.151.631) 250.001.121.963"
    ]
    
    # Regex for space-separated table rows with code and numbers
    pat = re.compile(r"^(.*?)\s+(\d{1,3}[a-z]?)\s+((?:\(?[\d\.,-]+\)?\s*){1,4})$")
    
    converted = []
    for l in lines:
        if "|" in l:
            converted.append(l)
        else:
            m = pat.match(l.strip())
            if m:
                item = m.group(1).strip()
                code = m.group(2).strip()
                nums = m.group(3).strip().split()
                converted.append(f"{item} | {code} | " + " | ".join(nums))
            elif re.match(r"^[I|V|X\d\.\-\s]+[A-Za-zÀ-ỹ]", l.strip()):
                # Section heading within table
                converted.append(f"| {l.strip()}")
            else:
                converted.append(l)
                
    for c in converted:
        print(c)

if __name__ == "__main__":
    test_conversion()
