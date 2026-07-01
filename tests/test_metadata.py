from hikmicropy.fusion import read_datetime_original


def test_datetime_parsed_from_filename():
    # EXIF が読めない場合でも HM<YYYYMMDDhhmm...> ファイル名から日時を復元する
    assert read_datetime_original("HM20200102030405.jpeg") == "2020/01/02 03:04"
