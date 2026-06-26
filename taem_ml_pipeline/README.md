# TAEM ML Pipeline

Bu paket iki hedef için hazırlandı:

1. En iyi fizik-tabanlı branch'i sabitlemek
2. Çoklu run sweep üreterek `taem_lb_score` için eğitim verisi toplamak ve baseline ML modeli kurmak

## İçerik

- `generate_taem_sweep_plan.py` : Referans branch etrafında çoklu run planı üretir.
- `run_taem_sweep.py` : Planı çalıştırır, her run için simülasyon + postprocess + Q1 analiz çıktıları üretir.
- `build_taem_ml_dataset.py` : Sweep çıktılarından araç-bazlı ML veri kümesi kurar.
- `train_taem_lb_baseline.py` : `taem_lb_score` için baseline regressor eğitir.
- `reference_best/` : Sabitlenecek referans branch dosyaları.
