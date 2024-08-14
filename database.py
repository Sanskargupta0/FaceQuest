import sqlite3
from config import DATABASE_FILE

def get_db_connection():
    conn = sqlite3.connect(DATABASE_FILE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.executescript('''
            CREATE TABLE IF NOT EXISTS finds (
                id INTEGER PRIMARY KEY, 
                telegram_user_id INTEGER, 
                original_image TEXT, 
                find_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                photos_found INTEGER, 
                dataset_total_images INTEGER
            );
            CREATE TABLE IF NOT EXISTS uploads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_user_id INTEGER NOT NULL,
                upload_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                photos_uploaded INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS uploaded_photos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                upload_id INTEGER,
                photo_path TEXT NOT NULL,
                FOREIGN KEY (upload_id) REFERENCES uploads (id)
            );
            CREATE TABLE IF NOT EXISTS found_photos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                find_id INTEGER,
                photo_path TEXT NOT NULL,
                FOREIGN KEY (find_id) REFERENCES finds (id)
            );
            CREATE TABLE IF NOT EXISTS jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                status TEXT NOT NULL,
                photo_filename TEXT NOT NULL,
                user_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                last_sent_match_id INTEGER DEFAULT 0,
                Processing_message_sent BOOLEAN DEFAULT FALSE,
                match_count INTEGER DEFAULT 0,
                images_processed INTEGER DEFAULT 0,
                total_images INTEGER DEFAULT 0,
                find_id INTEGER,
                error_message TEXT,
                message TEXT,
                search BOOLEAN DEFAULT FALSE,
                waiting_for_user BOOLEAN DEFAULT FALSE
            );
        ''')

def add_find_entry(user_id, original_image, total_images):
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute('INSERT INTO finds (telegram_user_id, original_image, photos_found, dataset_total_images) VALUES (?, ?, 0, ?)',
                    (user_id, original_image, total_images))
        find_id = cur.lastrowid
    return find_id

def update_find_results(find_id, photos_found):
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute('UPDATE finds SET photos_found = ? WHERE id = ?', (photos_found, find_id))

def update_found_photos(find_id, photos_found, dataset_total_images):
    # add the found photos in the current number of found photos
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute('UPDATE finds SET photos_found = COALESCE(photos_found, 0) + ? WHERE id = ?', (photos_found, find_id))
        cur.execute('UPDATE finds SET dataset_total_images = ? WHERE id = ?', (dataset_total_images, find_id))

def add_upload_entry(user_id, file_path):
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute('INSERT OR REPLACE INTO uploads (telegram_user_id, photos_uploaded) VALUES (?, COALESCE((SELECT photos_uploaded FROM uploads WHERE telegram_user_id = ?) + 1, 1))',
                    (user_id, user_id))
        upload_id = cur.lastrowid
        cur.execute('INSERT INTO uploaded_photos (upload_id, photo_path) VALUES (?, ?)', (upload_id, file_path))
    return upload_id

def get_user_upload_count(user_id):
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute('SELECT photos_uploaded FROM uploads WHERE telegram_user_id = ?', (user_id,))
        result = cur.fetchone()
    return result['photos_uploaded'] if result else 0

def add_job_entry(job_data):
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute('INSERT INTO jobs (status, photo_filename, user_id, name, find_id, total_images) VALUES (?, ?, ?, ?, ?, ?)',
                    (job_data['status'], job_data['photo_filename'], job_data['user_id'], job_data['name'], job_data['find_id'], job_data['total_images']))
        job_id = cur.lastrowid
    return job_id

def read_job_entry(job_id):
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute('SELECT * FROM jobs WHERE id = ?', (job_id,))
        result = cur.fetchone()
    return dict(result) if result else None

def update_processing_message_sent(job_id, value):
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute('UPDATE jobs SET Processing_message_sent = ? WHERE id = ?', (value, job_id))

def update_last_sent_match_id(job_id, value):
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute('UPDATE jobs SET last_sent_match_id = ? WHERE id = ?', (value, job_id))

def update_job_entry(job_id, updated_data):
    with get_db_connection() as conn:
        cur = conn.cursor()
        for key, value in updated_data.items():
            cur.execute(f'UPDATE jobs SET {key} = ? WHERE id = ?', (value, job_id))
            

def get_pending_jobs():
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute('SELECT id FROM jobs WHERE status = "pending"')
        result = cur.fetchall()
    return result

def delete_job_entry(job_id):
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute('DELETE FROM jobs WHERE id = ?', (job_id,))

def finds_id_with_original_image(original_image):
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute('SELECT id , dataset_total_images FROM finds WHERE original_image = ?', (original_image,))
        result = cur.fetchone()
    return result

def delete_find_entry(find_id):
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute('DELETE FROM finds WHERE id = ?', (find_id,))