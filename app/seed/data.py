"""Static seed data mirrored from the frontend mockData.js."""

VILLAGE = {
    # Bare names, not "Desa Kopo"/"Kabupaten Bogor" -- every letter template
    # (LETTERHEAD's "PEMERINTAH KABUPATEN {{ kabupaten }}"/"DESA {{ village_name }}",
    # and every pdf_body_template's "Kepala Desa {{ village_name }} ...
    # Kabupaten {{ kabupaten }}") already supplies the "Desa"/"Kabupaten"
    # prefix itself; a prefixed value here doubles it ("KABUPATEN KABUPATEN
    # BOGOR"). kecamatan was already bare ("Cisarua") -- this just matches it.
    "name": "Kopo", "slogan": "Kopo Kita", "kecamatan": "Cisarua",
    "kabupaten": "Bogor", "provinsi": "Jawa Barat",
}

# (nik_suffix, name, kk_suffix, rt, rw) — from mockData.js masterData
RESIDENTS = [
    ("0003", "Siti Rohmah", "7890", "002", "001"),
    ("0011", "Ahmad Fauzi", "1204", "001", "001"),
    ("0027", "Andi Wijaya", "5567", "003", "002"),
    ("0042", "Dewi Lestari", "8890", "004", "002"),
    ("0058", "Bambang Sujarwo", "3321", "002", "003"),
    ("0064", "Rina Handayani", "4410", "003", "001"),
    ("0071", "Sugeng Riyadi", "2290", "001", "004"),
    ("0085", "Yanto Prasetyo", "6631", "002", "002"),
    ("0092", "Wahyuni", "7742", "004", "003"),
    ("0106", "Slamet Riadi", "8853", "001", "001"),
    ("0114", "Kartika Sari", "9964", "002", "004"),
    ("0129", "Joko Purnomo", "1075", "003", "002"),
    ("0137", "Fitriani", "2186", "001", "003"),
    ("0145", "Agus Setiawan", "3297", "004", "001"),
    ("0153", "Maya Puspita", "4308", "003", "004"),
    ("0168", "Hendra Gunawan", "5419", "001", "002"),
    ("0176", "Lilis Suryani", "6520", "002", "003"),
    ("0184", "Rudi Hartono", "7631", "003", "001"),
    ("0192", "Nia Ramadhani", "8742", "004", "004"),
    ("0207", "Eko Prasetyo", "9853", "002", "002"),
    ("0215", "Wati Suminar", "1064", "003", "003"),
    ("0223", "Dedi Kurniawan", "2175", "001", "001"),
    ("0231", "Sri Wahyuni", "3286", "002", "004"),
    ("0248", "Tono Sudrajat", "4397", "004", "002"),
    ("0256", "Yeni Marlina", "5408", "001", "003"),
    ("0264", "Asep Saepudin", "6519", "002", "001"),
    ("0272", "Nining Kusrini", "7620", "003", "004"),
    ("0289", "Budi Santoso", "8731", "001", "002"),
    ("0297", "Nur Aini", "9842", "004", "001"),
    ("0305", "Dewi Anggraeni", "1053", "002", "003"),
    ("0313", "Sutrisno", "2164", "001", "004"),
    ("0321", "Ratna Kusuma", "3275", "003", "002"),
    ("0338", "Wawan Kurniadi", "4386", "001", "001"),
    ("0346", "Indah Permatasari", "5497", "004", "003"),
    ("0354", "Hari Mulyono", "6508", "002", "004"),
    ("0362", "Ani Setiawati", "7619", "003", "002"),
]
