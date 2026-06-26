B6 Figure Polish Package v3

Bu sürüm, v2'de görülen şu hatayı düzeltir:
FileNotFoundError: store\data_saved\phase2_B6_publication_figuressss

Neden oldu?
- Script trajectory CSV ararken store\data_saved altını taradı.
- Bu sırada bozuk/silinmiş/yanlış isimli bir alt klasöre denk geldi.
- v2 bu durumu yakalamadığı için Figure 1-4 yazılmış olsa bile script sonunda durdu.

v3 neyi değiştirir?
1) Bozuk/missing klasörleri atlar.
2) Figure 5 ground-track bulunamazsa script durmaz.
3) B5F timeout/no-CSV satırlarında All-NaN uyarısı oluşturmaz.
4) Ek olarak güvenli skip BAT dosyası verir.

Dosyalar
--------
phase2_B6_figure_polish_package.py
run_phase2_B6_figure_polish_package.bat
run_phase2_B6_figure_polish_package_skip_groundtrack.bat

Kurulum
-------
Bu dosyaları proje köküne kopyalayın:

D:\savunma-makale-adımlar\savunma makale-2.adım\EntryGuidance-master

Çalıştırma
----------
Önce normal:
.\run_phase2_B6_figure_polish_package.bat

Eğer yine ground-track aramasında sorun yaşarsanız:
.\run_phase2_B6_figure_polish_package_skip_groundtrack.bat

Çıktılar
--------
store\data_saved\phase2_B6_publication_figures_polished

Not
---
Skip-groundtrack modu Figure 5'i üretmez; Figure 1-4 ve caption/manifest dosyalarını üretir.
Makale için zorunlu ana B6 kanıt figürleri zaten Figure 1-4'tür.
