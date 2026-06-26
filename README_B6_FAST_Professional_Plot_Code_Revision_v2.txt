B6 FAST Professional Plot Code Revision v2
==========================================

Bu paket, önceki professional-label trajectory scriptinin uzun süre bekleme sorununu düzeltir.

Neden gerekli?
--------------
Önceki phase2_B6_trajectory_figures.py store/data_saved altında geniş tarama yapabiliyor ve bazı büyük CSV dosyalarını pandas ile okurken birkaç dakika takılabiliyordu. Bu sürüm varsayılan olarak geniş recursive search yapmaz.

Ana düzeltmeler
---------------
1) Representative success trajectory olarak B5E/B5F seçilmesini engeller.
2) Önce bilinen başarılı B5D combined CSV aranır.
3) Bulamazsa mevcut trajectory inventory CSV üzerinden B5D/tight-local seçer.
4) Geniş arama yalnızca --allow-search verilirse yapılır.
5) Etiketler profesyoneldir: Vehicle 1/2/3, range-to-go, altitude, bank angle.

Kopyalama
---------
Şu iki/üç dosyayı proje köküne kopyalayın ve mevcut trajectory scriptinin üzerine yazın:

D:\savunma-makale-adımlar\savunma makale-2.adım\EntryGuidance-master

- phase2_B6_trajectory_figures.py
- run_phase2_B6_trajectory_figures_professional_FAST.bat
- run_phase2_B6_trajectory_figures_professional_FAST_manual.bat

Çalıştırma
----------
Önce:

.\run_phase2_B6_trajectory_figures_professional_FAST.bat

Eğer B5D success CSV bulunamadı derse manual BAT içindeki SUCCESS_CSV satırını doğru combined CSV ile değiştirip şunu çalıştırın:

.\run_phase2_B6_trajectory_figures_professional_FAST_manual.bat

Çıktı klasörü
-------------
store\data_saved\phase2_B6_trajectory_figures_professional_fast

Not
---
Bu paket yalnızca plot/post-processing kodunu değiştirir. Guidance, multiset veya simülasyon mantığını değiştirmez.
