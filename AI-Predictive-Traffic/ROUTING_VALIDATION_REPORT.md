# Comprehensive Routing Validation Report

## 1. Overview & Objectives
This report documents the exhaustive verification matrix of all 4 configured dashboard starting locations across every hospital defined in the Mangaluru digital twin road network (`presentation_selection2.net.xml`).

### Starting Locations Evaluated:
1. `-26209727#1` (Starting Point 1)
2. `1213225868` (Starting Point 2)
3. `-1154699531` (Starting Point 3)
4. `1096889856` (Starting Point 4 - Default Base)

## 2. Summary Results
- **Total Combinations Tested**: 64
- **PASS (Routable with Valid Connected Paths & Candidates)**: 52
- **FAIL (Unroutable due to Network Topology or Missing Edge)**: 12

> [!NOTE]
> Of the 16 POIs loaded in `HospitalManager`, 13 are valid accessible medical facilities. All 13 accessible hospitals passed with 100% success rate across all 4 starting locations (52/52 combinations). The remaining 3 entries (`city_hospital`, `6938916238`, `6938916239`) represent POIs whose coordinates fall outside the passenger network bounding threshold; these are properly flagged `available: false` by `api/main.py` and disabled in the dashboard.

## 3. Father Muller Hospital Special Verification
Previously, Father Muller Hospital was assigned to `-184750315#2`, which has zero incoming connections in the SUMO network, causing all trips to fail.
- **Verified Destination Edge**: `26209723#3`
- **Edge Validity**: Edge exists in `presentation_selection2.net.xml`, length 40.73m, 1 passenger lane, shape `[(2093.5, 1196.56), (2108.78, 1159.08)]`.
- **Results after fix**:
  - `-26209727#1` -> `26209723#3`: PASS (20 edges, 1231.0m, 4 candidates)
  - `1213225868` -> `26209723#3`: PASS (15 edges, 1176.2m, 4 candidates)
  - `-1154699531` -> `26209723#3`: PASS (12 edges, 829.2m, 3 candidates)
  - `1096889856` -> `26209723#3`: PASS (6 edges, 172.4m, 2 candidates)

## 4. Full Validation Matrix

| Starting Edge | Hospital ID | Hospital Name | Destination Edge | Status | Edges | Distance (m) | Candidates | Notes |
|---|---|---|---|---|---|---|---|---|
| `-26209727#1` | `highland_hospital` | Highland Hospital | `-26299202#3` | **PASS** | 15 | 885.2 | 4 | Route found (15 edges, 885.2m), 4 candidates |
| `1213225868` | `highland_hospital` | Highland Hospital | `-26299202#3` | **PASS** | 20 | 1012.4 | 4 | Route found (20 edges, 1012.4m), 4 candidates |
| `-1154699531` | `highland_hospital` | Highland Hospital | `-26299202#3` | **PASS** | 13 | 1057.9 | 4 | Route found (13 edges, 1057.9m), 4 candidates |
| `1096889856` | `highland_hospital` | Highland Hospital | `-26299202#3` | **PASS** | 8 | 421.8 | 2 | Route found (8 edges, 421.8m), 2 candidates |
| `-26209727#1` | `kmc_hospital` | KMC Hospital | `1538932912#4` | **PASS** | 8 | 748.7 | 3 | Route found (8 edges, 748.7m), 3 candidates |
| `1213225868` | `kmc_hospital` | KMC Hospital | `1538932912#4` | **PASS** | 8 | 669.8 | 1 | Route found (8 edges, 669.8m), 1 candidates |
| `-1154699531` | `kmc_hospital` | KMC Hospital | `1538932912#4` | **PASS** | 10 | 1467.1 | 4 | Route found (10 edges, 1467.1m), 4 candidates |
| `1096889856` | `kmc_hospital` | KMC Hospital | `1538932912#4` | **PASS** | 17 | 1352.7 | 4 | Route found (17 edges, 1352.7m), 4 candidates |
| `-26209727#1` | `city_hospital` | City Hospital | `None` | **FAIL** | - | - | - | No nearest passenger edge reachable in network |
| `1213225868` | `city_hospital` | City Hospital | `None` | **FAIL** | - | - | - | No nearest passenger edge reachable in network |
| `-1154699531` | `city_hospital` | City Hospital | `None` | **FAIL** | - | - | - | No nearest passenger edge reachable in network |
| `1096889856` | `city_hospital` | City Hospital | `None` | **FAIL** | - | - | - | No nearest passenger edge reachable in network |
| `-26209727#1` | `1203949837` | Hospital (1203949837) | `184750315#2` | **PASS** | 20 | 1807.1 | 4 | Route found (20 edges, 1807.1m), 4 candidates |
| `1213225868` | `1203949837` | Hospital (1203949837) | `184750315#2` | **PASS** | 15 | 1752.3 | 4 | Route found (15 edges, 1752.3m), 4 candidates |
| `-1154699531` | `1203949837` | Hospital (1203949837) | `184750315#2` | **PASS** | 12 | 1405.2 | 3 | Route found (12 edges, 1405.2m), 3 candidates |
| `1096889856` | `1203949837` | Hospital (1203949837) | `184750315#2` | **PASS** | 3 | 634.2 | 1 | Route found (3 edges, 634.2m), 1 candidates |
| `-26209727#1` | `father_muller_hospital` | Father Muller Hospital | `26209723#3` | **PASS** | 20 | 1231.0 | 4 | Route found (20 edges, 1231.0m), 4 candidates |
| `1213225868` | `father_muller_hospital` | Father Muller Hospital | `26209723#3` | **PASS** | 15 | 1176.2 | 4 | Route found (15 edges, 1176.2m), 4 candidates |
| `-1154699531` | `father_muller_hospital` | Father Muller Hospital | `26209723#3` | **PASS** | 12 | 829.2 | 3 | Route found (12 edges, 829.2m), 3 candidates |
| `1096889856` | `father_muller_hospital` | Father Muller Hospital | `26209723#3` | **PASS** | 6 | 172.4 | 2 | Route found (6 edges, 172.4m), 2 candidates |
| `-26209727#1` | `160262590` | Hospital (160262590) | `-239271492#3` | **PASS** | 13 | 1841.9 | 3 | Route found (13 edges, 1841.9m), 3 candidates |
| `1213225868` | `160262590` | Hospital (160262590) | `-239271492#3` | **PASS** | 4 | 946.4 | 2 | Route found (4 edges, 946.4m), 2 candidates |
| `-1154699531` | `160262590` | Hospital (160262590) | `-239271492#3` | **PASS** | 15 | 2560.3 | 4 | Route found (15 edges, 2560.3m), 4 candidates |
| `1096889856` | `160262590` | Hospital (160262590) | `-239271492#3` | **PASS** | 22 | 2445.9 | 4 | Route found (22 edges, 2445.9m), 4 candidates |
| `-26209727#1` | `calaco_hospital` | Calaco Hospital | `322815830#0` | **PASS** | 16 | 1672.0 | 4 | Route found (16 edges, 1672.0m), 4 candidates |
| `1213225868` | `calaco_hospital` | Calaco Hospital | `322815830#0` | **PASS** | 10 | 928.8 | 4 | Route found (10 edges, 928.8m), 4 candidates |
| `-1154699531` | `calaco_hospital` | Calaco Hospital | `322815830#0` | **PASS** | 5 | 694.5 | 3 | Route found (5 edges, 694.5m), 3 candidates |
| `1096889856` | `calaco_hospital` | Calaco Hospital | `322815830#0` | **PASS** | 13 | 783.8 | 4 | Route found (13 edges, 783.8m), 4 candidates |
| `-26209727#1` | `scs_hospital` | SCS Hospital | `1189020224#0` | **PASS** | 16 | 1486.2 | 4 | Route found (16 edges, 1486.2m), 4 candidates |
| `1213225868` | `scs_hospital` | SCS Hospital | `1189020224#0` | **PASS** | 10 | 743.0 | 4 | Route found (10 edges, 743.0m), 4 candidates |
| `-1154699531` | `scs_hospital` | SCS Hospital | `1189020224#0` | **PASS** | 7 | 935.8 | 3 | Route found (7 edges, 935.8m), 3 candidates |
| `1096889856` | `scs_hospital` | SCS Hospital | `1189020224#0` | **PASS** | 15 | 1025.1 | 4 | Route found (15 edges, 1025.1m), 4 candidates |
| `-26209727#1` | `unity_hospital` | Unity hospital | `-1213275018` | **PASS** | 15 | 974.5 | 4 | Route found (15 edges, 974.5m), 4 candidates |
| `1213225868` | `unity_hospital` | Unity hospital | `-1213275018` | **PASS** | 18 | 981.0 | 4 | Route found (18 edges, 981.0m), 4 candidates |
| `-1154699531` | `unity_hospital` | Unity hospital | `-1213275018` | **PASS** | 13 | 1220.7 | 4 | Route found (13 edges, 1220.7m), 4 candidates |
| `1096889856` | `unity_hospital` | Unity hospital | `-1213275018` | **PASS** | 14 | 824.2 | 4 | Route found (14 edges, 824.2m), 4 candidates |
| `-26209727#1` | `indira_hospital` | Indira Hospital | `-26299195#5` | **PASS** | 5 | 475.1 | 3 | Route found (5 edges, 475.1m), 3 candidates |
| `1213225868` | `indira_hospital` | Indira Hospital | `-26299195#5` | **PASS** | 13 | 1197.4 | 4 | Route found (13 edges, 1197.4m), 4 candidates |
| `-1154699531` | `indira_hospital` | Indira Hospital | `-26299195#5` | **PASS** | 23 | 1619.5 | 4 | Route found (23 edges, 1619.5m), 4 candidates |
| `1096889856` | `indira_hospital` | Indira Hospital | `-26299195#5` | **PASS** | 18 | 983.4 | 4 | Route found (18 edges, 983.4m), 4 candidates |
| `-26209727#1` | `athena_hospital` | Athena Hospital | `26209730#0` | **PASS** | 4 | 266.2 | 3 | Route found (4 edges, 266.2m), 3 candidates |
| `1213225868` | `athena_hospital` | Athena Hospital | `26209730#0` | **PASS** | 12 | 988.6 | 4 | Route found (12 edges, 988.6m), 4 candidates |
| `-1154699531` | `athena_hospital` | Athena Hospital | `26209730#0` | **PASS** | 24 | 1697.7 | 4 | Route found (24 edges, 1697.7m), 4 candidates |
| `1096889856` | `athena_hospital` | Athena Hospital | `26209730#0` | **PASS** | 19 | 1061.6 | 4 | Route found (19 edges, 1061.6m), 4 candidates |
| `-26209727#1` | `5867851072` | Clinic (5867851072) | `1369161860#0` | **PASS** | 16 | 1574.0 | 4 | Route found (16 edges, 1574.0m), 4 candidates |
| `1213225868` | `5867851072` | Clinic (5867851072) | `1369161860#0` | **PASS** | 10 | 830.8 | 4 | Route found (10 edges, 830.8m), 4 candidates |
| `-1154699531` | `5867851072` | Clinic (5867851072) | `1369161860#0` | **PASS** | 7 | 1023.6 | 3 | Route found (7 edges, 1023.6m), 3 candidates |
| `1096889856` | `5867851072` | Clinic (5867851072) | `1369161860#0` | **PASS** | 15 | 1112.9 | 4 | Route found (15 edges, 1112.9m), 4 candidates |
| `-26209727#1` | `vijaya_clinic_general_hospital` | Vijaya Clinic General Hospital | `26299206#3` | **PASS** | 9 | 1093.1 | 3 | Route found (9 edges, 1093.1m), 3 candidates |
| `1213225868` | `vijaya_clinic_general_hospital` | Vijaya Clinic General Hospital | `26299206#3` | **PASS** | 9 | 1014.2 | 1 | Route found (9 edges, 1014.2m), 1 candidates |
| `-1154699531` | `vijaya_clinic_general_hospital` | Vijaya Clinic General Hospital | `26299206#3` | **PASS** | 11 | 1811.5 | 4 | Route found (11 edges, 1811.5m), 4 candidates |
| `1096889856` | `vijaya_clinic_general_hospital` | Vijaya Clinic General Hospital | `26299206#3` | **PASS** | 18 | 1697.1 | 4 | Route found (18 edges, 1697.1m), 4 candidates |
| `-26209727#1` | `6938916238` | Hospital (6938916238) | `None` | **FAIL** | - | - | - | No nearest passenger edge reachable in network |
| `1213225868` | `6938916238` | Hospital (6938916238) | `None` | **FAIL** | - | - | - | No nearest passenger edge reachable in network |
| `-1154699531` | `6938916238` | Hospital (6938916238) | `None` | **FAIL** | - | - | - | No nearest passenger edge reachable in network |
| `1096889856` | `6938916238` | Hospital (6938916238) | `None` | **FAIL** | - | - | - | No nearest passenger edge reachable in network |
| `-26209727#1` | `6938916239` | Clinic (6938916239) | `None` | **FAIL** | - | - | - | No nearest passenger edge reachable in network |
| `1213225868` | `6938916239` | Clinic (6938916239) | `None` | **FAIL** | - | - | - | No nearest passenger edge reachable in network |
| `-1154699531` | `6938916239` | Clinic (6938916239) | `None` | **FAIL** | - | - | - | No nearest passenger edge reachable in network |
| `1096889856` | `6938916239` | Clinic (6938916239) | `None` | **FAIL** | - | - | - | No nearest passenger edge reachable in network |
| `-26209727#1` | `mangalore_nursing_home` | Mangalore Nursing Home | `-1218977869` | **PASS** | 14 | 1450.2 | 4 | Route found (14 edges, 1450.2m), 4 candidates |
| `1213225868` | `mangalore_nursing_home` | Mangalore Nursing Home | `-1218977869` | **PASS** | 8 | 707.0 | 3 | Route found (8 edges, 707.0m), 3 candidates |
| `-1154699531` | `mangalore_nursing_home` | Mangalore Nursing Home | `-1218977869` | **PASS** | 8 | 1119.5 | 2 | Route found (8 edges, 1119.5m), 2 candidates |
| `1096889856` | `mangalore_nursing_home` | Mangalore Nursing Home | `-1218977869` | **PASS** | 16 | 1208.7 | 4 | Route found (16 edges, 1208.7m), 4 candidates |

## 5. Candidate-Route Quality Assessment
- **Start & Destination Alignment**: Every candidate begins strictly at the requested origin edge and terminates at the designated destination edge.
- **Topological Continuity**: Verified via `sumolib`: each successive edge connects via valid junctions without network disconnects.
- **Route 0 Authority**: Route 0 is guaranteed to be the primary authoritative route assigned to the ambulance.
- **Alternative Distinction**: Alternative routes (1-3) provide distinct feasible detours and are strictly restricted to visualization (blue = primary, red = alternatives).
- **Old Route Cleanup**: Old polygons and candidates are properly removed upon trip reset and subsequent dispatches.