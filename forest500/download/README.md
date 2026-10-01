# Forest 500's own downloads

Forest 500 (Global Canopy) gives its yearly masterfiles only through the form on
https://forest500.org/forest-500-data-methods/ . The owner downloaded every one on
2 October 2026 (companies 2017 to 2025, financial institutions 2016 to 2025, and the
2022 country selection).

- country_selection_data_2022.xlsx is kept here as downloaded; scripts/forest500_map.py
  reads it.
- The masterfile zips are large; the part of each row that describes the company or
  institution was read from them by scripts/forest500_details.py into
  forest500/details.json. To read them again, upload the zips here as downloaded and
  run forest500_details with FOREST500_DETAILS=1.

Forest 500 assessment data [Year], Global Canopy, Forest500.org (CC BY-NC 4.0).
