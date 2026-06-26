B6 Trajectory Figures Package

Amaç
----
B6 summary/polish figürlerinin üzerine fiziksel trajectory figürleri üretir:
1) Representative successful 2D ground track
2) Representative successful 3D trajectory, PNG/PDF
3) Interactive 3D trajectory HTML, Plotly varsa
4) TAEM approach time-history
5) Optional success-vs-failure-boundary ground-track comparison
6) Candidate inventory CSV

Önemli
------
Bu paket yeni simülasyon çalıştırmaz.
Guidance/multiset dosyalarını değiştirmez.
Sadece mevcut trajectory CSV dosyalarından grafik çıkarır.

Kurulum
-------
ZIP içindeki dosyaları proje köküne kopyalayın:

D:\savunma-makale-adımlar\savunma makale-2.adım\EntryGuidance-master

Çalıştırma - otomatik
---------------------
PowerShell:

cd "D:\savunma-makale-adımlar\savunma makale-2.adım\EntryGuidance-master"
.\run_phase2_B6_trajectory_figures_auto.bat

Çalıştırma - manuel CSV
-----------------------
Otomatik seçim yanlış dosya seçerse:

1) run_phase2_B6_trajectory_figures_manual_TEMPLATE.bat dosyasını açın.
2) SUCCESS_CSV ve FAILURE_CSV satırlarını gerçek CSV yollarıyla değiştirin.
3) BAT dosyasını çalıştırın.

Doğrudan Python örneği:

python phase2_B6_trajectory_figures.py --success-csv "store\data_saved\...\success.csv" --failure-csv "store\data_saved\...\failure.csv"

Çıktılar
--------
store\data_saved\phase2_B6_trajectory_figures

Beklenen dosyalar
-----------------
figT01_success_ground_track.png/pdf
figT02_success_3d_trajectory_static.png/pdf
figT02_success_3d_trajectory_interactive.html
figT03_taem_approach_time_history.png/pdf
figT04_success_vs_failure_ground_track.png/pdf, if a boundary CSV exists
trajectory_candidate_inventory.csv
phase2_B6_trajectory_figure_captions.txt
phase2_B6_trajectory_manifest.json

Makale kullanımı
----------------
Ana makaleye önerilen trajectory figürleri:
- figT01_success_ground_track
- figT02_success_3d_trajectory_static
- figT03_taem_approach_time_history

Supplementary için:
- figT02_success_3d_trajectory_interactive.html
- figT04_success_vs_failure_ground_track
- trajectory_candidate_inventory.csv

Not
---
Otomatik seçim, dosya adlarında B5D / tight_local / local_envelope / PASS_STRICT geçen CSV'leri pozitif başarı figürü için önceliklendirir.
B5E/B5F geçen CSV'leri failure-boundary karşılaştırması için önceliklendirir.
