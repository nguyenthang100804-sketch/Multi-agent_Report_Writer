"""Supplementary note headings must not turn into primary statements."""
import unittest

from src.ingestion.document_parser import detect_heading_line, step4_detect_structure
from src.schemas.document_schema import Block


def text_block(index: int, text: str) -> Block:
    return Block(block_id=f"blk_{index}", block_type="text",
                 physical_page_start=index, physical_page_end=index,
                 printed_pages=[str(index)], section="UNKNOWN", section_title="",
                 unit="VND", text=text)


class NotesSectionClassificationTests(unittest.TestCase):
    def test_supplementary_headings_are_notes(self):
        for title in (
            "V. THÔNG TIN BỔ SUNG CHO CÁC KHOẢN MỤC TRÌNH BÀY TRONG BẢNG CÂN ĐỐI KẾ TOÁN HỢP NHẤT",
            "VI. THÔNG TIN BỔ SUNG CHO CÁC KHOẢN MỤC TRÌNH BÀY TRONG BÁO CÁO KẾT QUẢ HOẠT ĐỘNG KINH DOANH",
            "VII. THÔNG TIN BỔ SUNG CHO CÁC KHOẢN MỤC TRÌNH BÀY TRONG BÁO CÁO LƯU CHUYỂN TIỀN TỆ HỢP NHẤT",
        ):
            self.assertEqual(detect_heading_line(title)[0], "NOTES")

    def test_note_state_requires_new_primary_form_to_switch(self):
        blocks = [text_block(1, "BẢN THUYẾT MINH BÁO CÁO TÀI CHÍNH HỢP NHẤT"),
                  text_block(2, "VI. THÔNG TIN BỔ SUNG CHO CÁC KHOẢN MỤC TRÌNH BÀY TRONG BÁO CÁO KẾT QUẢ HOẠT ĐỘNG KINH DOANH"),
                  text_block(3, "BÁO CÁO LƯU CHUYỂN TIỀN TỆ HỢP NHẤT"),
                  text_block(4, "Mẫu B 02 - DN\nBÁO CÁO KẾT QUẢ HOẠT ĐỘNG KINH DOANH")]
        result, _, _ = step4_detect_structure(blocks, "BANK_2025_Hopnhat.txt")
        self.assertEqual([block.section for block in result[:4]],
                         ["NOTES", "NOTES", "NOTES", "INCOME_STATEMENT"])

    def test_note_form_b09_does_not_authorize_primary_heading(self):
        blocks = [text_block(1, "THUYẾT MINH BÁO CÁO TÀI CHÍNH HỢP NHẤT"),
                  text_block(2, "Mẫu B 09 - DN/HN\nBáo cáo kết quả hoạt động kinh doanh hợp nhất."),
                  text_block(3, "Mẫu số B09 - DN/HN\nBảng cân đối kế toán riêng"),
                  text_block(4, "Mẫu B 01 - DN/HN\nBẢNG CÂN ĐỐI KẾ TOÁN")]
        result, _, _ = step4_detect_structure(blocks, "MCH_2024_Hopnhat.txt")
        self.assertEqual([block.section for block in result],
                         ["NOTES", "NOTES", "NOTES", "BALANCE_SHEET"])

    def test_bank_primary_forms_can_follow_notes(self):
        blocks = [text_block(1, "THUYẾT MINH BÁO CÁO TÀI CHÍNH HỢP NHẤT"),
                  text_block(2, "Mẫu số: B02/TCTD-HN\nBÁO CÁO TÌNH HÌNH TÀI CHÍNH HỢP NHẤT")]
        result, _, _ = step4_detect_structure(blocks, "NVB_2022_Hopnhat.txt")
        self.assertEqual([block.section for block in result], ["NOTES", "BALANCE_SHEET"])


if __name__ == "__main__":
    unittest.main()
