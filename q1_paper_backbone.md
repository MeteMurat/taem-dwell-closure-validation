# Q1 Makale Hattı — Başlangıç Omurgası

## Çalışma başlığı için aday
**Event-Based TAEM Evaluation for Same-Target Multi-Vehicle Entry Guidance: A Dwell-Consistent Terminal Proximity Framework**

## Ana iddia
Bu çalışma yalnızca çoklu araç simülasyonu sunmaz. Aynı hedefe yönelen üç entry aracında terminal başarının, tek bir son-konum metriği ile değil, dwell tabanlı TAEM-event ve sürekli proximity metrikleri ile ayrıştırılabildiğini gösterir.

## Özgün katkılar
1. TAEM için dwell destekli, tekrar üretilebilir bir event tanımı.
2. `taem_close_score` / `box_score` ile sürekli terminal yakınlık ölçümü.
3. Aynı hedefe yönelen üç araç altında terminal rejim ayrıştırması.
4. Başarıya çok yaklaşan ancak latch üretemeyen near-success rejimlerinin nicel gösterimi.
5. Guidance tasarımından ayrıştırılabilen bir event/logging/evaluation katmanı.

## Bölüm omurgası
### 1. Introduction
- Problem: terminal başarıyı yalnızca touchdown ya da final state ile vermek yetersizdir.
- Gap: TAEM-benzeri terminal olay tanımları çoğu çalışmada tekrar üretilebilir event mantığıyla verilmez.
- Contribution: dwell-tabanlı event + continuous proximity + same-target multi-vehicle comparison.

### 2. Problem Definition and Terminal Success Formulation
- Görev senaryosu ve aynı hedefe giden üç araç
- TAEM state set: h, v, s_go, psi
- Tolerans kutusu
- Dwell tabanlı success event
- Continuous proximity metric (`taem_close_score`, `box_score`)

### 3. Methodology
- Guidance/simulation yapısı
- Event/logging/evaluation pipeline
- Araç bazlı rota shaping mantığı
- Koşu ve karşılaştırma protokolü

### 4. Results and Discussion
- Baseline multi-vehicle davranış
- TAEM proximity ve event sonuçları
- Vehicle-wise failure mode classification
- Patch/ablation progression
- Constraint-aware discussion

### 5. Conclusion
- Event-based TAEM çerçevesi çalıştı
- Araçlar terminal rejimler açısından nicel ayrıştırıldı
- Tam latch üretimi bir sonraki guidance refinement hedefi olarak kaldı

## Kod sprinti ile makale hattı nasıl bağlanacak
Bu sprintte yalnızca mis1 için tek değişkenli bank-freeze denenecek. Amaç ilk `taem_in_box` / `taem_reached` üretmek. Makale tarafında ise 3 araçlı düzen ve event-based analiz sabit tutulacak.
