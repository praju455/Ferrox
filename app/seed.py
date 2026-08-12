from app.db import SessionLocal, init_db
from app.models import Product
from app.services.ingestion import IngestionService
from app.core.config import get_settings


MOCK_PRODUCTS = [
    ("Aurora End-Suction Pump AXP-200", ["Manufacturer: Aurora Industrial. Model: AXP-200. Flow rate 120 GPM. 50 ft head. 5 HP. Material cast iron.", "Brand Aurora Industrial Model AXP-200 pump, 115 GPM, 48 ft head, stainless steel impeller."]),
    ("Borex Bearing BR-6205", ["Manufacturer: Borex. Model: BR-6205 bearing. Bore: 25 mm. OD: 52 mm. Load: 14 kN. Material chrome steel.", "Borex 6205 sealed bearing, bore 25mm, outside diameter 52 mm, load 12 kN."]),
    ("VoltEdge Motor VM-10", ["Manufacturer: VoltEdge. Model: VM-10 motor. 10 HP. 230 V. 3 phase. 1750 RPM. TEFC.", "VoltEdge VM10 electric motor 7.5 HP, 230V, 3 phase, 1725 RPM, TEFC."]),
    ("ForgeMax Hex Bolt HX-050", ["Manufacturer: ForgeMax. Part number HX-050 bolt. Diameter: 1/2 in. Length: 2 in. Thread: 13 UNC. Material zinc plated steel. Grade 5."]),
    ("HydroWorks Pump HP-75", ["Make HydroWorks Model HP-75. Flow rate 75 GPM. 40 ft head. 3 HP.", "HydroWorks HP-75 catalog says 80 GPM and cast iron body."]),
    ("Precision Bearing PB-302", ["Manufacturer: Precision Bearing. Model: PB-302 bearing. Bore: 30 mm. OD: 62 mm. Material chrome steel."]),
    ("TorquePro Motor TP-5", ["Brand TorquePro. Model: TP-5. 5 HP. 460 V. 3 phase. 1800 RPM.", "TorquePro TP-5 ODP enclosure, 1750 rpm."]),
    ("SteelCore Screw SC-188", ["Manufacturer: SteelCore. Part number SC-188 screw. Diameter: 3/8 in. Length: 1.25 in. Thread: 16 UNC. Material stainless steel."]),
    ("Atlas Pump AP-900", ["Manufacturer: Atlas. Model: AP-900. Flow rate 300 GPM. 95 ft head. 20 HP. Material cast iron.", "Atlas website lists AP-900 at 280 GPM and 90 ft head."]),
    ("Northstar Bearing NS-40", ["Manufacturer: Northstar. Model: NS-40 bearing. Bore: 40 mm. Load: 22 kN. Material chrome steel."]),
    ("RotorX Motor RX-2", ["Manufacturer: RotorX. Model: RX-2 motor. 2 HP. 120 V. 1 phase. 3450 RPM."]),
    ("BoltWorks BW-10", ["Brand BoltWorks. Part number BW-10. Diameter: 10 mm. Length: 40 mm. Thread pitch: 1.5 mm. Grade 8.8."]),
    ("ClearFlow Pump CFP-44", ["Manufacturer: ClearFlow. Model: CFP-44. Flow rate 44 GPM. Material stainless steel.", "CFP-44 datasheet: 45 GPM, 28 ft head, 1 HP."]),
    ("LoadKing Bearing LK-80", ["Manufacturer: LoadKing. Model: LK-80 bearing. Bore: 80 mm. OD: 140 mm. Load: 55 kN."]),
    ("PhaseLine Motor PL-15", ["Manufacturer: PhaseLine. Model: PL-15. 15 HP. 460 V. 3 phase. IP55.", "PhaseLine PL-15 marketing page says 20 HP."]),
    ("Titan Fastener TF-625", ["Manufacturer: Titan. Part number TF-625 bolt. Diameter: 5/8 in. Length: 4 in. Material carbon steel. Grade 8."]),
]


def seed() -> None:
    init_db()
    db = SessionLocal()
    ingestion = IngestionService(get_settings())
    try:
        for name, snippets in MOCK_PRODUCTS:
            product = Product(name=name)
            db.add(product)
            db.flush()
            for index, snippet in enumerate(snippets, start=1):
                db.add(ingestion.from_text(product.id, snippet, f"mock-source-{index}"))
        db.commit()
    finally:
        db.close()


if __name__ == "__main__":
    seed()
