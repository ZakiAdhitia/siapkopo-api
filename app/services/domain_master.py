"""Read-only CRUD services for the per-letter-type domain master tables.

Each service only needs `.list()` (see app/api/v1/domain_master.py) --
these tables are written exclusively by SubmissionService._save_to_domain_master
on issuance, never through this service's `.create()`/`.update()`.
"""
from app.models.master import (
    MasterDomisili,
    MasterKelahiran,
    MasterKematian,
    MasterKK,
    MasterNA,
    MasterPindah,
    MasterSKU,
    MasterUbahData,
    MasterUHC,
)
from app.services.master import _CrudService


class MasterDomisiliService(_CrudService):
    model = MasterDomisili
    name = "Master Domisili"

    @property
    def search_columns(self):
        return [MasterDomisili.nik, MasterDomisili.nama]


class MasterKelahiranService(_CrudService):
    model = MasterKelahiran
    name = "Master Kelahiran"

    @property
    def search_columns(self):
        return [MasterKelahiran.nama_anak, MasterKelahiran.nik_ayah, MasterKelahiran.nik_ibu]


class MasterKematianService(_CrudService):
    model = MasterKematian
    name = "Master Kematian"

    @property
    def search_columns(self):
        return [MasterKematian.nik, MasterKematian.nama]


class MasterSKUService(_CrudService):
    model = MasterSKU
    name = "Master SKU"

    @property
    def search_columns(self):
        return [MasterSKU.nik, MasterSKU.nama]


class MasterNAService(_CrudService):
    model = MasterNA
    name = "Master NA"

    @property
    def search_columns(self):
        return [MasterNA.nik, MasterNA.nama, MasterNA.nik_csi]


class MasterUHCService(_CrudService):
    model = MasterUHC
    name = "Master UHC"

    @property
    def search_columns(self):
        return [MasterUHC.nik_pasien, MasterUHC.nama_pasien]


class MasterPindahService(_CrudService):
    model = MasterPindah
    name = "Master Pindah"

    @property
    def search_columns(self):
        return [MasterPindah.nik_pemohon, MasterPindah.nama_pemohon]


class MasterKKService(_CrudService):
    model = MasterKK
    name = "Master KK"

    @property
    def search_columns(self):
        return [MasterKK.no_kk, MasterKK.nama_kk]


class MasterUbahDataService(_CrudService):
    model = MasterUbahData
    name = "Master Ubah Data"

    @property
    def search_columns(self):
        return [MasterUbahData.nik, MasterUbahData.nama]
