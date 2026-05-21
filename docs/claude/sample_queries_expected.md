# Expected Intent — 20 Câu Quan Trọng Nhất

Dùng làm ground-truth khi review kết quả `compare_chat_pipeline`.  
Mỗi dòng ghi: `input_kind`, `location_mode`, `location_status`, và slot chính.

> **Ghi chú**: "expected" ở đây là hành vi *đúng về nghĩa* — tức là kết quả mà cả v1 lẫn v2 nên hội tụ về.  
> Nếu v1 và v2 đều sai so với expected → cần sửa cả hai.  
> Nếu chỉ một phía sai → phía đó cần fix.

---

## 1. `1 Sư Vạn Hạnh, Phường 9, Quận 5, TP HCM`

| Trường | Expected |
|--------|----------|
| `input_kind` | `specific_address` |
| `location_mode` | `near_anchor` |
| `location_status` | `ok` (sau khi geocode hoặc cache hit) |
| `location_phrase` | `1 Su Van Hanh, Phuong 9, Quan 5, TP HCM` (full address giữ nguyên) |
| Slots | không có budget, guest_count, amenities |

**Lý do quan trọng**: Địa chỉ số nhà đầy đủ — phải giữ nguyên chuỗi, không rút gọn thành quận.

---

## 2. `gần Landmark 81`

| Trường | Expected |
|--------|----------|
| `input_kind` | `landmark_or_poi` |
| `location_mode` | `near_anchor` |
| `location_status` | `ok` (PlaceReference cache hit hoặc geocode) |
| `anchor_name` | `Landmark 81` hoặc tương đương |
| Slots | không có budget, guest_count |

**Lý do quan trọng**: POI nổi tiếng — phải resolve thành near_anchor OK, không phải AMBIGUOUS.  
Hiện tại v2 đang trả AMBIGUOUS → **đây là gap cần fix**.

---

## 3. `gần quán cafe ở Quận 5`

| Trường | Expected |
|--------|----------|
| `input_kind` | `generic_poi_in_area` |
| `location_mode` | `area` (fallback về quận vì cafe không có tọa độ cụ thể) |
| `location_status` | `ok` |
| `area` | `quan 5` |
| `nearby_poi_key` | `cafe` |

**Lý do quan trọng**: Không geocode "quán cafe" → dùng quận làm anchor, gắn tag nearby_poi.

---

## 4. `Rex Hotel`

| Trường | Expected |
|--------|----------|
| `input_kind` | `hotel_name` |
| `location_mode` | `hotel_name` hoặc `near_anchor` (nếu resolve được tọa độ) |
| `location_status` | `ok` hoặc `unresolved` nếu không có trong cache |
| `hotel_name` | `Rex Hotel` |
| Slots | không có budget, amenities |

**Lý do quan trọng**: Tên khách sạn cụ thể — phải giữ lại `hotel_name`, không convert sang `area`.

---

## 5. `Quận 3`

| Trường | Expected |
|--------|----------|
| `input_kind` | `area` |
| `location_mode` | `area` |
| `location_status` | `ok` |
| `area` | `quan 3` (normalized) hoặc `Quận 3` (display) |
| Slots | không có budget, guest_count, amenities |

**Lý do quan trọng**: Area thuần — không gọi geocoder. v1 và v2 phải đồng nhất.

---

## 6. `có parking`

| Trường | Expected |
|--------|----------|
| `input_kind` | `amenity_only` |
| `location_mode` | `unknown` |
| `location_status` | `unresolved` |
| `required_amenities` | `["parking"]` |
| Slots | không có area, budget, guest_count |

**Lý do quan trọng**: Amenity thuần, **không phải location**. v1 đang sai (trả `landmark`).

---

## 7. `có chỗ đậu xe`

| Trường | Expected |
|--------|----------|
| `input_kind` | `amenity_only` |
| `location_mode` | `unknown` |
| `location_status` | `unresolved` |
| `required_amenities` | `["parking"]` |

**Lý do quan trọng**: Variant tiếng Việt của "có parking" — phải cho kết quả đồng nhất.

---

## 8. `khách sạn gần Landmark 81 dưới 1tr5 cho 2 người có wifi`

| Trường | Expected |
|--------|----------|
| `input_kind` | `mixed_search` |
| `location_mode` | `near_anchor` |
| `location_status` | `ok` |
| `budget_max` | `1_500_000` |
| `guest_count` | `2` |
| `required_amenities` | `["wifi"]` |
| `accommodation_types` | `["hotel"]` |

**Lý do quan trọng**: Câu phức hợp đầy đủ — phải extract đúng tất cả 5 slot.

---

## 9. `ở đâu cũng được miễn dưới 700k`

| Trường | Expected |
|--------|----------|
| `input_kind` | `unknown` hoặc `mixed_search` |
| `location_mode` | `anywhere` |
| `location_status` | `ok` |
| `budget_max` | `700_000` |

**Lý do quan trọng**: ANYWHERE + budget — location phải là anywhere, budget phải được extract.

---

## 10. `gần tôi có wifi`

| Trường | Expected |
|--------|----------|
| `input_kind` | `mixed_search` hoặc `amenity_only` |
| `location_mode` | `near_user` |
| `location_status` | `unresolved` (không có GPS) hoặc `ok` (có GPS) |
| `required_amenities` | `["wifi"]` |
| `debug.needs_user_location` | `true` khi không có GPS |

**Lý do quan trọng**: Near-user cần GPS — không có GPS thì status=unresolved, có GPS thì OK.

---

## 11. `homestay quận 3 dưới 800k có máy lạnh`

| Trường | Expected |
|--------|----------|
| `input_kind` | `mixed_search` |
| `location_mode` | `area` |
| `location_status` | `ok` |
| `area` | `quan 3` |
| `budget_max` | `800_000` |
| `required_amenities` | `["air_conditioner"]` |
| `accommodation_types` | `["homestay"]` |

---

## 12. `gần bệnh viện ở Bình Thạnh`

| Trường | Expected |
|--------|----------|
| `input_kind` | `generic_poi_in_area` |
| `location_mode` | `area` |
| `location_status` | `ok` |
| `area` | `binh thanh` |
| `nearby_poi_key` | `hospital` |

---

## 13. `xin chào`

| Trường | Expected |
|--------|----------|
| `input_kind` | `greeting` |
| `location_mode` | `unknown` |
| `location_status` | `unresolved` |
| Slots | tất cả None / rỗng |

**Lý do quan trọng**: Greeting thuần — không được recommend, không extract slot.

---

## 14. `gan Landmark 81` (không dấu)

| Trường | Expected |
|--------|----------|
| `input_kind` | `landmark_or_poi` |
| `location_mode` | `near_anchor` |
| `location_status` | `ok` |

**Lý do quan trọng**: Phải xử lý được tiếng Việt không dấu giống có dấu.

---

## 15. `o dau cung duoc` (không dấu)

| Trường | Expected |
|--------|----------|
| `input_kind` | `unknown` (v2 hiện tại) hoặc bất kỳ |
| `location_mode` | `anywhere` |
| `location_status` | `ok` |

**Lý do quan trọng**: ANYWHERE pattern phải nhận ra cả dạng không dấu.

---

## 16. `phòng trọ Bình Thạnh dưới 4 triệu có wifi`

| Trường | Expected |
|--------|----------|
| `input_kind` | `mixed_search` |
| `location_mode` | `area` |
| `area` | `binh thanh` |
| `budget_max` | `4_000_000` |
| `required_amenities` | `["wifi"]` |
| `accommodation_types` | `["hostel"]` hoặc `["apartment"]` |

---

## 17. `villa Đà Lạt 4 người có hồ bơi riêng cuối tuần`

| Trường | Expected |
|--------|----------|
| `input_kind` | `mixed_search` |
| `location_mode` | `area` |
| `area` | `da lat` |
| `guest_count` | `4` |
| `required_amenities` | `["pool"]` |
| `accommodation_types` | bao gồm `"villa"` hoặc tương đương |

---

## 18. `khach san gan Nha tho Duc Ba duoi 1tr2 cho 2 nguoi co wifi` (không dấu)

| Trường | Expected |
|--------|----------|
| `input_kind` | `mixed_search` |
| `location_mode` | `near_anchor` |
| `location_status` | `ok` |
| `budget_max` | `1_200_000` |
| `guest_count` | `2` |
| `required_amenities` | `["wifi"]` |
| `accommodation_types` | `["hotel"]` |

**Lý do quan trọng**: Câu không dấu phức tạp — phải extract đúng tất cả slot.

---

## 19. `Resort gần biển Đà Nẵng 3 ngày 2 đêm`

| Trường | Expected |
|--------|----------|
| `input_kind` | `mixed_search` |
| `location_mode` | `area` hoặc `near_anchor` (tùy cache) |
| `area` | `da nang` |
| `trip_days` | `3` hoặc `2` (ngày/đêm) |
| `accommodation_types` | `["resort"]` hoặc tương đương |

---

## 20. `gần đây có hồ bơi` (near-user + amenity)

| Trường | Expected |
|--------|----------|
| `input_kind` | `mixed_search` hoặc `amenity_only` |
| `location_mode` | `near_user` |
| `location_status` | `unresolved` (không có GPS) |
| `required_amenities` | `["pool"]` |
| `debug.needs_user_location` | `true` |

**Lý do quan trọng**: "gần đây" = near_user. Có amenity thêm → không block recommendation (có filter khác).

---

## Tóm tắt Gap Đã Biết (từ compare run)

| Nhóm | v1 | v2 | Verdict |
|------|----|----|---------|
| amenity_only ("có parking") | `landmark`, status=unresolved | `amenity_only`, status=unresolved | **v2 đúng hơn** |
| area ("Quận 3") | `landmark`, area="Quận 3" (có dấu) | `area`, area="quan 3" (norm) | **v2 đúng hơn** |
| landmark ("gần Landmark 81") | `landmark`, near_anchor, ok | `landmark_or_poi`, ambiguous | **v1 đúng hơn** — v2 cần fix PlaceReference hit |
| hotel_name ("Rex Hotel") | `hotel_name`, unknown, unresolved | `hotel_name`, ambiguous | v1 gần đúng hơn |
| anywhere ("ở đâu cũng được") | `landmark`, anywhere, unresolved | `unknown`, anywhere, ok | v2 đúng status=ok, v1 đúng input_kind |
| mixed + landmark ("khách sạn gần…") | `landmark`, near_anchor, ok | `mixed_search`, ambiguous | **v1 đúng location**, v2 đúng input_kind |
| generic_poi_in_area | `landmark`, unresolved | `generic_poi_in_area`, area ok | **v2 đúng hơn** nhưng `area` bị "quan cafe" thay vì "quan 5" |
