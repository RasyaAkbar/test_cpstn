/* Penjelasan singkat dalam bahasa sehari-hari untuk tiap KPI, ditampilkan saat kursor diarahkan
   ke nama KPI. Key harus sama dengan key di backend/app/modules/evaluasi/kpi.py.
   KPI baru yang belum ada di sini memakai deskripsi dari backend. */

export const KPI_EXPLANATION: Record<string, string> = {
  projects_late: 'Berapa proyek yang diperkirakan selesai setelah tanggal target. Idealnya 0.',
  sv_total_days: 'Total keterlambatan semua proyek, dalam hari kerja. Proyek yang lebih cepat dari target dihitung 0, jadi tidak mengurangi total.',
  sv_max_days: 'Keterlambatan proyek yang paling telat. Angka negatif berarti semua proyek selesai lebih cepat dari target.',
  on_time_probability: 'Peluang proyek selesai tepat waktu, dihitung dari simulasi yang diulang berkali-kali. Baru muncul kalau replikasi lebih dari 0.',
  rli_peak: 'Beban kerja anggota paling berat dalam satu minggu. 1,0 berarti pas dengan kapasitasnya; di atas 1,0 berarti kelebihan beban.',
  overload_resource_weeks: 'Berapa kali anggota kelebihan beban dalam seminggu. Satu anggota yang overload 3 minggu dihitung 3.',
  wbi: 'Seberapa merata beban kerja antar anggota. Mendekati 1 berarti beban terbagi rata; makin rendah berarti ada yang bekerja jauh lebih berat dari yang lain.',
  soi_max: 'Mengukur anggota yang overload terus-menerus (minimal 2 minggu berturut-turut). Makin tinggi, makin lama dan makin parah overload-nya.',
  sustained_overload_resources: 'Jumlah anggota yang overload berturut-turut minimal 2 minggu. Mereka paling berisiko kelelahan.',
  cdi_max: 'Seberapa jauh keterlambatan satu task menular ke task-task sesudahnya. Angka tertinggi menunjuk task yang paling berbahaya kalau telat.',
  blocked_ratio: 'Persentase waktu kerja yang terbuang karena task tertahan dan tidak ada pekerjaan lain sebagai pengganti.',
  reallocated_ratio: 'Dari waktu menunggu, berapa persen yang berhasil dipakai untuk mengerjakan task lain yang tidak saling bergantung. Makin tinggi makin baik.',
};