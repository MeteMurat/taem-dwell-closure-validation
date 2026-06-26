B6 Trajectory Figures Package v2
================================

Amaç
----
Bu paket, B6 bounded-local-U3 anlatısı için trajectory odaklı figürleri mevcut CSV çıktılarından üretir.
Bu sürüm (v2), önceki otomatik seçim sorunlarını düzeltir.

v2 farkları
-----------
1. Success CSV seçimi yalnızca B5D / tight-local-envelope benzeri klasörlerle sınırlandı.
2. Failure-boundary CSV seçimi yalnızca B5E veya B5F klasörleriyle sınırlandı.
3. Gerçek B5E/B5F boundary trajectory bulunamazsa Figure T4 otomatik olarak atlanır.
4. Bank-angle paneli radyan benzeri değerleri dereceye çevirir.
5. TAEM marker yoksa TAEM-proxy marker kullanılır.

Üretilen figürler
-----------------
- figT01_success_ground_track
- figT02_success_3d_trajectory_static
- figT02_success_3d_trajectory_interactive.html (Plotly varsa)
- figT03_taem_approach_time_history
- figT04_success_vs_failure_ground_track (yalnızca gerçek B5E/B5F boundary varsa)
- trajectory_candidate_inventory.csv
- phase2_B6_trajectory_figure_captions.txt
- phase2_B6_trajectory_manifest.json

Önerilen çalışma sırası
-----------------------
1) Önce inventory:
   run_phase2_B6_trajectory_candidate_inventory_v2.bat

2) Sonra auto üretim:
   run_phase2_B6_trajectory_figures_auto_v2.bat

3) Gerekirse manual seçim:
   run_phase2_B6_trajectory_figures_manual_TEMPLATE_v2.bat

Not
---
Bu paket yalnızca post-processing yapar. Simülasyon çalıştırmaz ve guidance dosyalarını değiştirmez.
