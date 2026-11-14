"""Reviewed transcription of Tables 2–9, NTRS 20110008636, PDF pages 5–7.

Each tuple contains one reported (ULOI, MOC) pair, both oxygen volume percent.
Pairs repeated in different tables are intentionally retained with their context.
Blank 'testing in progress' cells do not become measurements. Table 1 is a
material/configuration inventory, not a 22-material oxygen-limit dataset.
"""
SOURCE = "https://ntrs.nasa.gov/citations/20110008636"


def ground_rows():
    rows = []

    def add(table, material, configuration, uloi, moc, thickness_in=None, diameter_in=None):
        footnote = table in {2, 6} and material in {"PET", "PEI"}
        rows.append({"measurement_id": f"NTRS-20110008636:T{table}:{len(rows)+1}",
                     "source_record": "NTRS-20110008636", "table_number": table,
                     "pdf_page": 5 if table <= 4 else 6 if table <= 6 else 7,
                     "material": material, "configuration": configuration,
                     "thickness_mm": round(thickness_in * 25.4, 6) if thickness_in is not None else "",
                     "diameter_mm": round(diameter_in * 25.4, 6) if diameter_in is not None else "",
                     "uloi_oxygen_pct": uloi, "moc_oxygen_pct": moc,
                     "gravity_regime": "earth_1g", "role": "earth_comparison_only",
                     "pressure_kpa": "" if footnote else 101.352932,
                     "pressure_note": "See Table 2 footnote a: PET/PEI 10.2 psia and hot-wire GRC protocol; mode-specific pressure needs review" if footnote else "Paper default 14.7 psia unless otherwise noted",
                     "source_url": SOURCE, "extraction_method": "manual_transcription_checked_against_pdf_tables"})

    # Table 2: chemical igniter, then hot wire.
    for material, thickness, diameter, values in [
        ("PET", None, None, (21.5,20,21.3,20)), ("PEI", None,None,(26.5,24,23.5,23)),
        ("MQ",.040,None,(23.4,22,22.5,21)), ("MQ",.024,None,(22.8,20,22.4,20)),
        ("PI",None,None,(27.2,26,28.7,27)), ("PEEK",None,None,(20.8,20.1,22,21.1)),
        ("PMMA",None,.25,(19.5,19,18.9,18)),
    ]:
        for index, mode in enumerate(["chemical igniter", "hot wire"]):
            add(2,material,mode + ("; extruded rod" if material == "PMMA" else ""),*values[index*2:index*2+2],thickness,diameter)
    for mil, uloi, moc in [(4,17.5,17),(10,19.7,18),(14,21,19),(24,22.8,20),(40,23.4,22)]:
        add(3,"MQ",f"{mil} mil thickness",uloi,moc,mil/1000)
    for durometer, uloi, moc in [(30,28.1,26),(40,26.8,26),(50,27.4,24),(60,27.2,26),(70,29.5,29)]:
        add(4,"MQ",f"{durometer} durometer",uloi,moc,.25)
    for material, values in [("MQ",(20.9,20,22.4,21)),("PI",(27.3,26,28.6,27)),
                             ("NBR",(16.6,16.1,16.5,16.1)),("PEI",(21.9,21,22.5,22)),("PVC",(40.1,35,41.8,39))]:
        for index, mounting in enumerate(["standard mounting", "exposed edge"]):
            add(5,material,mounting+"; 7 inch sample",*values[index*2:index*2+2],.060 if material=="MQ" else None)
    # Table 6: 1, 2 and 6 inch hot-wire criteria, then 6 inch chemical igniter.
    for material, values, thickness, diameter in [
        ("PET",[(15.8,15),(18.5,18),(21.3,20),(21.5,20)],None,None),
        ("PEI",[(22.5,22),(23.5,22),(23.5,23),(26.5,24)],None,None),
        ("PVC",[None,None,None,(45.2,40)],None,.125),
        ("PMMA",[None,None,(18.9,18),(19.5,19)],None,.25),
        ("MQ",[(18.6,18),(21.2,20),(22.5,21),(23.4,22)],.040,None),
        ("PI",[(26.3,25),(27.4,26),(28.7,27),(27.2,26)],None,None),
    ]:
        for pair, config in zip(values,["1 inch; hot wire","2 inch; hot wire","6 inch; hot wire","6 inch; chemical igniter"]):
            if pair:
                add(6,material,"pass/fail burn length "+config,*pair,thickness,diameter)
    for config, uloi, moc in [("extruded; hot wire",18.9,18),("cast; hot wire",15.7,14),("extruded; chemical igniter",19.5,19)]:
        add(7,"PMMA",config,uloi,moc,diameter_in=.25)
    for material, config, uloi, moc, diameter in [
        ("POM","Acetron GP; rod",12.9,12,.125),("POM","Acetron GP; 0.5 inch wide sheet",12.3,11,None),
        ("PP","rod",17.6,16,.125),("PVC","rod",45.2,40,.125),
        ("PA","Nylon 101; rod",21.9,20,.125),("PA","Zytel 42; 0.5 inch wide sheet",21.6,21,None),
    ]:
        add(8,material,config+"; 7 inch sample",uloi,moc,diameter_in=diameter)
    for material, values in [("PA",[(21.6,21),(24.5,24.1)]),("PET",[(22.6,21),(22.1,21)]),
                             ("POM",[(12.3,11),None]),("Epoxy/glass",[(17.9,16),(23.6,23)]),("PVC",[None,(40.1,35)])]:
        for pair, config in zip(values,["0.5 inch width","2.5 inch width; standard mounting"]):
            if pair:
                add(9,material,config+"; 7 inch sample",*pair)
    return rows
