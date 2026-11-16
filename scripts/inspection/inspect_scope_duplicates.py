import duckdb

c = duckdb.connect("data/facts_storage/financial_facts.duckdb", read_only=True)
print(c.execute("""SELECT ticker, scope, count(*) FROM financial_facts
    WHERE ticker IN ('DHG','PAP','VCR','FPT','GVR')
    GROUP BY 1,2 ORDER BY 1,2""").fetchall())
print(c.execute("""SELECT report_type,physical_page,label,current_year FROM financial_facts
    WHERE ticker='GVR' AND fiscal_year=2023 AND code='10'
    ORDER BY physical_page""").fetchall())
