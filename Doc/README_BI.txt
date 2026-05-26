Источник данных файлы Excel  в папках
\\10.1.19.245\C2M Logistics\2023
\\10.1.19.245\C2M Logistics\2024
\\10.1.19.245\C2M Logistics\2025

скрипты python в папке 
C:\Users\admin\Documents\BI_Analytics\Logistics

скрипт C2M_excel_search.py обходит папки, собирает файлы с определенным набором колонок
 
required_columns = ["cartonid", "itemid", "masterno", "ordercode", "consigneecountry", "service", "danger_type"]

атрибуты найденных файлов записывает в таблицу  TABLE_NAME = 'excel_registry'

скрипт C2M_excel_to_manifest.py на основании атрибутов в таблице excel_registry читает файл эксель, обрабатывает, записывает в таблицу db_target_table = 'manifest'  
помечает в реестре как прочитанный датавремя, (dt_processed = %s,) читает из реестра только новые файлы (датавремя - пусто)

Конечные данные для отчета - view представление Postgres 
DB_USER=postgres
DB_PASSWORD=root
DB_HOST=localhost
DB_PORT=5432
DB_NAME=Logistics

скрипты запускаются планировщиком Windows: C:\Users\admin\Documents\BI_Analytics\manifest.bat

Для отчета Битрикс работают скрипты
 btrx_fast_tasks.py
 btrx_tasks.bat
планировщик Windows

Отчеты pbix:
C:\Users\admin\Documents\BI_Analytics

c2m_logisctic.pbix - рабочая область в PBI Service - C2M Logistic
c2m_tariff.pbix - рабочая область  в PBI Service - c2m_tariff

планы преобразованы в Excel и записаны в базу
\\10.1.19.245\C2M Logistics\BI Analytics\Plan\План 2025 объёмы for db.xlsx


BI users

Эдуард Огай
eduard.ogai@antriagr.uz
Toku912280
------------------------------------------
Антон Григорьевский
anton.grigorevskii@antriagr.uz
Jaqa421627
------------------------------------------
Сардор Туляганов
sardor.tulyaganov@antriagr.uz
Qoyu777454
------------------------------------------
Алина Хон
alina.khon@antriagr.uz
Vusa878088
------------------------------------------
Абдумалик Назаров
abdumalik.nazarov@antriagr.uz
Mujo832770
------------------------------------------
Евгения Полякова
evgeniya.polyakova@antriagr.uz
Mada965817
------------------------------------------
Дмитрий Андрюхин
dmitrii.andryukhin@antriagr.uz
Puha691959
------------------------------------------
Никита Юнев
nikita.yunev@antriagr.uz
Hoya767978
==========================================
Эдуард Огай
Антон Григорьевский
Сардор Туляганов
Алина Хон
Абдумалик Назаров
Евгения Полякова
Дмитрий Андрюхин
Никита Юнев 


