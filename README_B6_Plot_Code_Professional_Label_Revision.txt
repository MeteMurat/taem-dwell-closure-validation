
B6 Plot Code Professional Label Revision
========================================

Bu paket, paylaştığınız plot dosyalarını makale figürlerinde görünen teknik/ham etiketleri temizleyecek şekilde revize eder.

Hangi dosyalar B6'daki ana 6 figürü üretiyor?
---------------------------------------------
- phase2_B6_make_publication_figures.py ana B6 yayın figürlerini üretir.
  Bu dosya Figure 1-6 seti için ana dosyadır:
  1) campaign success-rate
  2) failure-boundary summary
  3) B5E terminal-error diagnostic
  4) B5F range-closure diagnostic
  5) representative ground track
  6) representative 3D trajectory / HTML

Ek B6 trajectory figürleri:
- phase2_B6_trajectory_figures.py
  ground track, 3D trajectory, TAEM time-history ve success-vs-boundary figürlerini üretir.

Ek polished summary figürleri:
- phase2_B6_figure_polish_package.py

Genel rapor dosyaları:
- plot_csv_report.py
- plot_csv_report_TAEM.py
- plot_csv_report-23-01.py
- visualize_3d_anim_safe_fixed.py

Yapılan başlıca etiket değişiklikleri
--------------------------------------
- mis_id=0 / mis_id=1 / mis_id=2  -> Vehicle 1 / Vehicle 2 / Vehicle 3
- s_go start / s_go final          -> Initial range-to-go / Final range-to-go
- s_go axis labels                 -> Range-to-go
- Non-strict-pass rate             -> No strict TAEM closure
- Timeout rate                     -> Timeout or no terminal output
- B5F uzun case isimleri           -> Audit 1, Audit 2, Audit 3, Audit 4
- Height                           -> Altitude
- Teknik underscore'lu candidate isimleri -> Candidate 1, Candidate 2, ...

Kullanım
--------
Bu paketin içindeki .py ve .bat dosyalarını şu klasöre kopyalayın ve mevcut dosyaların üzerine yazın:

D:\savunma-makale-adımlar\savunma makale-2.adım\EntryGuidance-master

Önerilen çalıştırma sırası
--------------------------
1) Ana B6 yayın figürleri:
   .\run_phase2_B6_publication_figures_professional.bat

2) B6 polished figürleri:
   .\run_phase2_B6_figure_polish_professional.bat

3) B6 trajectory figürleri:
   .\run_phase2_B6_trajectory_figures_professional.bat

Genel CSV raporları için:
   .\run_plot_csv_report_professional_example.bat

Not
---
Bu paket yalnızca post-processing/plot dosyalarını değiştirir. Guidance, multiset, simülasyon veya hesaplama mantığını değiştirmez.
