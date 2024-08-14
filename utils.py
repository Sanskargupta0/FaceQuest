import os
from config import DIRECTORIES
import pickle
import cv2
import pickle
import face_recognition

ENCODING_FILE = "known_encodings_of_dataset.pickle"
DATASET_DIR = "./Dataset/"

def setup_directories():
    for directory in DIRECTORIES:
        if not os.path.exists(directory):
            os.makedirs(directory)
    if not os.path.exists("known_encodings.pickle"):
        with open("known_encodings.pickle", 'wb') as f:
            # adding empty list to the file
            pickle.dump([], f)
    if not os.path.exists(ENCODING_FILE):
        with open(ENCODING_FILE, 'wb') as f:
            # adding empty list to the file
            pickle.dump([], f)


def createEncodings(image):
    #Find face locations for all faces in an image
    face_locations = face_recognition.face_locations(image)

    #when no face is found
    if len(face_locations)==0:
        print("No face found in the image")
    
    #Create encodings for all faces in an image
    known_encodings=face_recognition.face_encodings(image,known_face_locations=face_locations)
    return known_encodings,face_locations

def save_encodings(encodings, image_paths):
    with open(ENCODING_FILE, "rb") as f:
        data = pickle.load(f)
    
    for encoding , image_path in zip(encodings, image_paths):
        data.append({"encoding": encoding, "image_path": image_path})
    
    with open(ENCODING_FILE, "wb") as f:
        pickle.dump(data, f)

def update_dataset_encodings():

    with open(ENCODING_FILE, "rb") as f:
        data = pickle.load(f)
    # last endcoding image path
    last_encoding_image_path = data[-1]["image_path"] if data else None

    # last image path in dataset
    last_image_path = os.listdir(DATASET_DIR)[-1] if os.listdir(DATASET_DIR) else None

    print(f"Last encoding image path: {last_encoding_image_path}")
    print(f"Last image path in dataset: {last_image_path}")
    if last_encoding_image_path == last_image_path:
        print("No new images in dataset")
    else:
        # get all images in dataset after last_image_path
        images = os.listdir(DATASET_DIR)
        for img in images:
            if img == last_encoding_image_path:
                new_image_index = images.index(img) + 1
                break
            else:
                new_image_index = 0
        
        encodings = []
        images_path = []
        for img in images[new_image_index:]:
            print(f"Processing {img}")
            image = cv2.imread(os.path.join(DATASET_DIR, img))
            image=cv2.resize(image,(0,0),fx=0.2,fy=0.2,interpolation=cv2.INTER_LINEAR)
            encs,locs=createEncodings(image)
            
            i=0
            for loc in locs:
                unknown_encoding=encs[i]
                i+=1
                encodings.append(unknown_encoding)
                images_path.append(img)
        print("Saving new encodings")
        save_encodings(encodings, images_path)



                
        
        
    
