import os
import cv2
import pickle
import numpy as np
import face_recognition
import time
from concurrent.futures import ThreadPoolExecutor
import mediapipe as mp
import logging
from database import (
    get_db_connection, update_job_entry, read_job_entry, 
    get_pending_jobs, update_find_results, finds_id_with_original_image, delete_find_entry, update_found_photos
)
from utils import update_dataset_encodings
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

EXECUTOR = ThreadPoolExecutor(max_workers=5)
ENCODING_FILE = "known_encodings.pickle"
PEOPLE_DIR = "./People/"

def save_encodings(encodings, image_paths):
    with open(ENCODING_FILE, "rb") as f:
        data = pickle.load(f)
    
    for encoding , image_path in zip(encodings, image_paths):
        data.append({"encoding": encoding, "image_path": image_path})
    
    with open(ENCODING_FILE, "wb") as f:
        pickle.dump(data, f)


def read_encodings(image_path):
    with open(ENCODING_FILE, "rb") as f:
        data = pickle.load(f)

    encodings = []
    
    for d in data:
        if d["image_path"] == image_path:
            encodings.append(d["encoding"])
    
    return encodings

def create_encodings(image):
    face_locations = face_recognition.face_locations(image)
    return face_recognition.face_encodings(image, known_face_locations=face_locations), face_locations



def compare_face_encodings(unknown_encoding, known_encoding, image_path, tolerance=0.5):
    matches = face_recognition.compare_faces(known_encoding, unknown_encoding, tolerance=tolerance)
    face_distances = face_recognition.face_distance(known_encoding, unknown_encoding)
    best_match_index = np.argmin(face_distances)
    
    if matches[best_match_index]:
        return True, image_path, face_distances[best_match_index]
    return False, "", 0.0

def process_known_people_images(img, encs, serach):
    # Checking if the same person face encoding is already present in the known_encodings.pickle file
    with open(ENCODING_FILE, "rb") as f:
        data = pickle.load(f)
    if not serach:
        for items in data:
            encodings = items["encoding"]
            if face_recognition.compare_faces(encodings, encs, tolerance=0.4):
                return items["image_path"]
        
    save_encodings([encs[0]], [img])
    return None

def process_dataset_images(job_data):
    try:
        known_encodings = read_encodings(job_data['photo_filename'])
        with open("known_encodings_of_dataset.pickle", "rb") as f:
            unknown_encodings = pickle.load(f)
    except Exception as e:
        logger.error(f"Error reading encodings: {e}")

    match_count = 0
    images_processed = 0
    
    with get_db_connection() as conn:
        cursor = conn.cursor()
        match_image_path = ""
        current_image_path = ""
        skip = False
        print("comming to this point")
        print(type(job_data['last_sent_match_id']))
        if job_data['last_sent_match_id']:
            print("comming to this point 2")
            print(job_data['find_id'])
            print(job_data['last_sent_match_id'])
            cursor.execute("SELECT photo_path FROM found_photos WHERE find_id = ? AND id = ?", (job_data['find_id'], job_data['last_sent_match_id']))
            match_image_path = cursor.fetchone()[0]
            print(match_image_path)
            skip = True
        for items in unknown_encodings:
            if skip:
                if items["image_path"] == match_image_path:
                    skip = False
                continue
            encoding = items["encoding"]
            image_path = items["image_path"]
            print(f"Processing {image_path}")
            if current_image_path != image_path:
                current_image_path = image_path
                images_processed += 1
            if match_image_path == image_path:
                continue
            else:
                print(images_processed)
                accept_bool, image_path, _ = compare_face_encodings(encoding, known_encodings, image_path)
                if accept_bool:
                    match_count += 1
                    match_image_path = image_path
                    cursor.execute("INSERT INTO found_photos (find_id, photo_path) VALUES (?, ?)", 
                                (job_data['find_id'], image_path))
                    conn.commit()
                    update_job_entry(job_data['id'], {'match_count': match_count, 'images_processed': images_processed})

        if job_data['last_sent_match_id']:
            update_found_photos(job_data['find_id'], match_count, job_data['total_images'])
        else:
            update_find_results(job_data['find_id'], match_count)
    
    return match_count




def count_fingers(image_path):
    mp_hands = mp.solutions.hands

    # Read the input image
    image = cv2.imread(image_path)
    
    with mp_hands.Hands(
        static_image_mode=True,
        max_num_hands=2,
        min_detection_confidence=0.5) as hands:

        # Convert the BGR image to RGB, flip the image around y-axis for correct handedness output
        image = cv2.cvtColor(cv2.flip(image, 1), cv2.COLOR_BGR2RGB)
        
        # To improve performance, optionally mark the image as not writeable to
        # pass by reference.
        image.flags.writeable = False
        results = hands.process(image)

        # Initially set finger count to 0
        finger_count = 0

        if results.multi_hand_landmarks:
            for hand_landmarks in results.multi_hand_landmarks:
                # Get hand index to check label (left or right)
                handIndex = results.multi_hand_landmarks.index(hand_landmarks)
                handLabel = results.multi_handedness[handIndex].classification[0].label

                # Set variable to keep landmarks positions (x and y)
                handLandmarks = []

                # Fill list with x and y positions of each landmark
                for landmarks in hand_landmarks.landmark:
                    handLandmarks.append([landmarks.x, landmarks.y])

                # Test conditions for each finger: Count is increased if finger is
                # considered raised.
                # Thumb: TIP x position must be greater or lower than IP x position,
                # depending on hand label.
                if handLabel == "Left" and handLandmarks[4][0] > handLandmarks[3][0]:
                    finger_count = finger_count+1
                elif handLabel == "Right" and handLandmarks[4][0] < handLandmarks[3][0]:
                    finger_count = finger_count+1

                # Other fingers: TIP y position must be lower than PIP y position,
                # as image origin is in the upper left corner.
                if handLandmarks[8][1] < handLandmarks[6][1]:  # Index finger
                    finger_count = finger_count+1
                if handLandmarks[12][1] < handLandmarks[10][1]:  # Middle finger
                    finger_count = finger_count+1
                if handLandmarks[16][1] < handLandmarks[14][1]:  # Ring finger
                    finger_count = finger_count+1
                if handLandmarks[20][1] < handLandmarks[18][1]:  # Pinky
                    finger_count = finger_count+1

    if finger_count == 0:
        return False, "No fingers detected in the image."
    elif finger_count == 2:
        return True,  "Two fingers detected in the image."
    else:
        return False, f"Expected 2 fingers, but found {finger_count} fingers."


def image_verification(img):
    try:
        # check only one face in the image
        image = cv2.imread(os.path.join(PEOPLE_DIR, img))
        image = cv2.resize(image,(0,0),fx=0.2,fy=0.2,interpolation=cv2.INTER_LINEAR)
        encodings, _ = create_encodings(image)
        if len(encodings) != 1:
            return False, "Only one face should be present in the image."
        else:
            result = count_fingers(os.path.join(PEOPLE_DIR, img))
            if result[0]:
                return True, result[1], encodings
            else:
                return False, result[1], encodings
    except Exception as e:
        return False, str(e)


def process_job(job_id):
    try:
        job_data = read_job_entry(job_id)
        photo_filename = job_data['photo_filename']
        
        logger.info(f"Processing job: {job_id}")

        logger.info(f"Processing {job_data['name']} image for comparison...")

        verify_result, message, encodings = image_verification(photo_filename)
        if not verify_result:
            logger.error(f"Image verification failed: {message}")
            update_job_entry(job_id, {'status': 'error', 'error_message': message})
            return

        image_path = process_known_people_images(photo_filename, encodings, job_data['search'])

        if image_path:
            logger.info(f"Same person face encoding already present in the known_encodings.pickle file. Skipping image processing.")
            result = finds_id_with_original_image(image_path)
            delete_find_entry(job_data['find_id'])
            if result['dataset_total_images'] < job_data['total_images']:
                update_job_entry(job_id, {'status': 'Dataset_Incressed', 'find_id': result['id']})
                return
            else:
                update_job_entry(job_id, {'status': 'Already_Processed', 'find_id': result['id']})
                return
        
        update_job_entry(job_id, {'status': 'processing'})

        logger.info("Processing dataset images...")

        print(job_data)

        match_count = process_dataset_images(job_data)

        update_job_entry(job_id, {'status': 'completed', 'match_count': match_count})
        
        logger.info(f"Job completed successfully. Match count: {match_count}")

    except Exception as e:
        logger.error(f"Error processing job: {str(e)}")
        update_job_entry(job_id, {'status': 'error', 'error_message': str(e)})

def main():
    update_dataset_encodings()
    while True:
        try:
            jobs = get_pending_jobs()
            for job in jobs:
                EXECUTOR.submit(process_job, job['id'])
            
            time.sleep(5)  # Check for new jobs every 5 seconds

        except Exception as e:
            logger.error(f"Error in main loop: {str(e)}")
            time.sleep(10)  # Wait for 10 seconds before retrying in case of an error

if __name__ == "__main__":
    main()