B6 Figure Polish Package v2

Amaç
----
Mevcut B5D/B5E/B5F çıktılarını kullanarak makale için daha temiz B6 figürleri üretir.

Önemli
------
Bu paket yeni simülasyon çalıştırmaz.
Guidance dosyasını değiştirmez.
Sadece post-processing yapar.

Dosyalar
--------
phase2_B6_figure_polish_package.py
run_phase2_B6_figure_polish_package.bat

Kurulum
-------
Bu iki dosyayı proje kök klasörüne kopyalayın:

D:\savunma-makale-adımlar\savunma makale-2.adım\EntryGuidance-master

Çalıştırma
----------
PowerShell:

cd "D:\savunma-makale-adımlar\savunma makale-2.adım\EntryGuidance-master"
.\run_phase2_B6_figure_polish_package.bat

Çıktılar
--------
store\data_saved\phase2_B6_publication_figures_polished

Beklenen ana çıktılar
---------------------
fig01_b6_success_rates_polished.png/pdf
fig02_b6_boundary_summary_polished.png/pdf
fig03a_b5e_height_error_polished.png/pdf
fig03b_b5e_velocity_error_polished.png/pdf
fig03c_b5e_sgo_error_polished.png/pdf
fig04_b5f_range_closure_polished.png/pdf
fig05_ground_track_polished.png/pdf
phase2_B6_polished_figure_captions.txt
phase2_B6_polished_manifest.json

Makale yorumu
-------------
B5D pozitif bounded-local U3 kanıtıdır.
B5E ve B5F pozitif evrensellik kanıtı değildir; failure-boundary / envelope limitation kanıtı olarak kullanılmalıdır.
