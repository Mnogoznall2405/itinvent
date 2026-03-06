import sys
import json
import os

sys.path.append(r"C:\Project\Image_scan\WEB-itinvent\backend")
from api.v1.vcs import _save_vcs_info

# Cleaned, parsed JSON data corresponding to the previously entered Markdown
json_data = [
  { "agent": "ППК ВСК (Тюмень)", "server": "tc.mo-vsk.ru", "login": "zsgp-tmn", "password": "p#NQK6TN", "contact1": "8-903-741-66-16 (Денис)\n8-499-390-34-34, доб. 4006 (Алексей)", "contact2": "kireev.am@mo-vsk.ru (Алексей)\nlunden.de@mo-vsk.ru (Денис, руков.)" },
  { "agent": "ППК ВСК (Санкт-Петербург)", "server": "tc.mo-vsk.ru", "login": "zsgp-spb", "password": "o6jRy$zQ", "contact1": "8-903-741-66-16 (Денис)\n8-499-390-34-34, доб. 4006 (Алексей)", "contact2": "kireev.am@mo-vsk.ru (Алексей)\nlunden.de@mo-vsk.ru (Денис, руков.)" },
  { "agent": "ФКП УЗКС (Тюмень, Первомайская)", "server": "tc.fkp-uzks.ru", "login": "zapsibgazgaz", "password": "7FqecjnM", "contact1": "8-495-540-94-70 доб.1911\n8-495-540-94-70 доб. 1911 или доб.1114 Кузнецов Игорь", "contact2": "it@fkp-uzks.ru\nigor.kuznetsov@fkp-uzks.ru (Кузнецов Игорь)" },
  { "agent": "ФКП УЗКС (Тюмень, Герцена)", "server": "tc.fkp-uzks.ru", "login": "zapsibgazgaz2", "password": "wFpA9dd2", "contact1": "8-495-540-94-70 доб.1911\n8-495-540-94-70 доб. 1911 или доб.1114 (Кузнецов И.)", "contact2": "it@fkp-uzks.ru\nigor.kuznetsov@fkp-uzks.ru (Кузнецов Игорь)" },
  { "agent": "ФКП УЗКС (Москва)", "server": "tc.fkp-uzks.ru", "login": "zapsibgaz", "password": "Vjandf44", "contact1": "8-495-540-94-70 доб.1911\n8-495-540-94-70 доб. 1911 или доб.1114 (Кузнецов И.)", "contact2": "it@fkp-uzks.ru\nigor.kuznetsov@fkp-uzks.ru (Кузнецов Игорь)" },
  { "agent": "ФКП УЗКС (Санкт-Петербург)", "server": "tc.fkp-uzks.ru", "login": "zapsibgazspb", "password": "mAkdig13", "contact1": "8-495-540-94-70 доб.1911\n8-495-540-94-70 доб. 1911 или доб.1114 (Кузнецов И.)", "contact2": "it@fkp-uzks.ru\nigor.kuznetsov@fkp-uzks.ru (Кузнецов Игорь)" },
  { "agent": "ДС МО (Тюмень)", "server": "79.133.91.15", "login": "zsgp-t", "password": "", "contact1": "8-495-696-75-27 (Данил Иванов)\n8-996-409-02-01\n8-916-630-21-69 (Юрий)", "contact2": "8-916-630-21-69 (Юрий)\nTelegram, WhatsApp" },
  { "agent": "ДС МО (Общая)", "server": "79.133.91.15", "login": "sibgazprom", "password": "", "contact1": "8-495-696-75-27 (Данил Иванов)\n8-996-409-02-01\n8-916-630-21-69 (Юрий)", "contact2": "8-916-630-21-69 (Юрий)\nTelegram, WhatsApp" },
  { "agent": "ДС МО (Санкт-Петербург)", "server": "79.133.91.15", "login": "zsgp-spb", "password": "12345678", "contact1": "8-495-696-75-27 (Данил Иванов)\n8-996-409-02-01\n8-916-630-21-69 (Юрий)", "contact2": "8-916-630-21-69 (Юрий)\nTelegram, WhatsApp" },
  { "agent": "ДС МО (Вологда)", "server": "79.133.91.15", "login": "scv-20", "password": "", "contact1": "8-495-696-75-27 (Данил Иванов)\n8-996-409-02-01\n8-916-630-21-69 (Юрий)", "contact2": "8-916-630-21-69 (Юрий)\nTelegram, WhatsApp" }
]

_save_vcs_info({"content": json.dumps(json_data, ensure_ascii=False)})
print("Successfully migrated vcs_info.json to JSON format!")
