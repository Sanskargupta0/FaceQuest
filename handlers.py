import sqlite3
import datetime
import logging
import os
from telegram import Update
from telegram.ext import CallbackContext, ConversationHandler
from config import CONVERSATION_STATES
from utils import update_dataset_encodings
from database import add_find_entry, get_user_upload_count, get_db_connection, add_job_entry, read_job_entry, delete_job_entry, update_job_entry

logger = logging.getLogger(__name__)

def start(update: Update, context: CallbackContext) -> int:
    update.message.reply_text(
        "Welcome to the Face Recognition Bot!\n"
        "Here's what you can do:\n"
        "• Type /1 or /find to start finding a person\n"
        "• Type /2 or /upload to add images to the dataset\n"
        "• Type /3 or /cancel to cancel the current operation"
    )
    return ConversationHandler.END

def find(update: Update, context: CallbackContext) -> int:
    update.message.reply_text("Please enter the name of the person you want to find:")
    if update.message.text == '/cancel' or update.message.text == '/3':
        return ConversationHandler.END
    return CONVERSATION_STATES['NAME']

def receive_name(update: Update, context: CallbackContext) -> int:
    if update.message.text == '/cancel' or update.message.text == '/3':
        return ConversationHandler.END
    if not update.message.text:
        update.message.reply_text("Please enter a valid name.")
        return CONVERSATION_STATES['NAME']
    context.user_data['name'] = update.message.text
    update.message.reply_text(f"Great! Now please send a selfie of the person you're looking for, showing a V symbol with your hand.")
    return CONVERSATION_STATES['SELFIE']

def receive_selfie(update: Update, context: CallbackContext) -> int:
    try:
        if update.message.text == '/cancel' or update.message.text == '/3':
            return ConversationHandler.END
        photo_file = update.message.photo[-1].get_file()
        date_time = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        photo_filename = f"{date_time}_{context.user_data['name']}.jpg"
        photo_path = os.path.join("./People", photo_filename)
        photo_file.download(photo_path)        

        job_data = {
            "status": "pending",
            "photo_filename": photo_filename,
            "user_id": update.effective_user.id,
            "name": context.user_data['name'],
            "last_sent_match_id": 0,
            "Processing_message_sent": False,
            "match_count": 0,
            "images_processed": 0
        }

        already_added_images = 0
        total_images = get_user_upload_count(update.effective_user.id)
        total_images = total_images + already_added_images
        job_data['total_images'] = total_images
        find_id = add_find_entry(update.effective_user.id, photo_filename, total_images)
        job_data['find_id'] = find_id

        job_id = add_job_entry(job_data)

        update.message.reply_text(
            "Your request has been received and is being processed.\n"
            "We'll notify you when we start processing and keep you updated on the progress."
        )
        
        context.job_queue.run_repeating(check_job_status, interval=10, first=5, context=(update.effective_user.id, job_id))

        return ConversationHandler.END
    except Exception as e:
        logger.error(f"Error in receive_selfie: {str(e)}")
        update.message.reply_text("An error occurred while processing your selfie. Please try again.")
        return CONVERSATION_STATES['SELFIE']

def upload(update: Update, context: CallbackContext) -> int:
    update.message.reply_text(
        "Please send the image(s) you want to add to the dataset.\n"
        "You can send multiple photos or documents containing images.\n"
        "Send /done when you're finished uploading. \n"
        "Send /cancel to cancel the operation."
    )
    context.user_data['upload_count'] = 0
    return CONVERSATION_STATES['DATASET']

def receive_dataset_image(update: Update, context: CallbackContext) -> int:
    try:
        if update.message.text == '/done'or update.message.text == '/cancel' or update.message.text == '/3':
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute('SELECT photos_uploaded FROM uploads WHERE telegram_user_id = ?', (update.effective_user.id,))
            result = cur.fetchone()
            result2 = result['photos_uploaded'] if result else 0
            conn.close()
            update.message.reply_text(f"Upload complete. {context.user_data['upload_count']} images added to the dataset. Total Images Uploaded by you {result2}  Thank you for contributing!")
            update_dataset_encodings()
            return ConversationHandler.END

        if update.message.document:
            file_ext = os.path.splitext(update.message.document.file_name)[1].lower()
            file = update.message.document.get_file()
            if file_ext not in ['.jpg', '.jpeg', '.png']:
                update.message.reply_text("Please upload only image files.")
                return CONVERSATION_STATES['DATASET']
            date_time = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            file_name = f"user_upload_photo_{update.effective_user.id}_{date_time}{file_ext}"
        elif update.message.photo:
            file = update.message.photo[-1].get_file()
            date_time = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            file_name = f"user_upload_photo_{update.effective_user.id}_{date_time}.jpg"
        else:
            update.message.reply_text("Please send photos or image documents.")
            return CONVERSATION_STATES['DATASET']

        file_path = os.path.join("Dataset", file_name)
        if file.download(file_path):
            conn = get_db_connection()
            cur = conn.cursor()
            telegram_user_id = update.effective_user.id
            # check if the user has uploaded photos before
            cur.execute('SELECT id FROM uploads WHERE telegram_user_id = ?', (telegram_user_id,))
            result = cur.fetchone()
            if not result:
                cur.execute('INSERT INTO uploads (telegram_user_id, photos_uploaded) VALUES (?, 0)', (telegram_user_id,))
                result2 = cur.lastrowid
                cur.execute('INSERT INTO uploaded_photos (upload_id, photo_path) VALUES (?,?)', (result2,file_path,))
            else:
                result2 = result['id']
                cur.execute('INSERT INTO uploaded_photos (upload_id, photo_path) VALUES (?,?)', (result2,file_path,))
            # increment the photos_uploaded column in the uploads table
            cur.execute('UPDATE uploads SET photos_uploaded = photos_uploaded + 1 WHERE id = ?', (result2,))
            conn.commit()
            conn.close()
            context.user_data['upload_count'] += 1
            update.message.reply_text("Image successfully added to the dataset!")
        else:
            update.message.reply_text(f"Error downloading image {update.message.document.file_name or 'photo'}. Please try again.")
        return CONVERSATION_STATES['DATASET']
    except Exception as e:
        logger.error(f"Error in receive_dataset_image: {str(e)}")
        update.message.reply_text("An error occurred while processing your image. Please try again.")
        return CONVERSATION_STATES['DATASET']

def cancel(update: Update, context: CallbackContext) -> int:
    update.message.reply_text("Operation cancelled. What would you like to do next?")
    return ConversationHandler.END

def global_message_handler(update: Update, context: CallbackContext):
    user_id = update.effective_user.id

    # Check if there's a job waiting for this user's input
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('SELECT id FROM jobs WHERE user_id = ? AND waiting_for_user = True', (user_id,))
    result = cur.fetchone()
    conn.close()

    if result:
        job_id = result[0]
        job_data = read_job_entry(job_id)

        if update.message.text in ['/y', 'y', '/Y', 'Y', 'yes', 'Yes', 'YES']:
            conn = get_db_connection()
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            cur.execute('SELECT id, photo_path FROM found_photos WHERE find_id = ?', (job_data['find_id'],))
            result = cur.fetchall()
            conn.close()

            if job_data['status'] == 'Dataset_Incressed':
                for match in result:
                    with open("./Dataset/"+match['photo_path'], 'rb') as photo_file:
                        update.message.reply_photo(photo_file)

                update.message.reply_text("Now searching in Recently Uploaded Pictures")
                update_job_entry(job_id, {'status': 'pending', 'search': True, 'last_sent_match_id': result[-1]['id'] if result else 0})
                # restart the job
                context.job_queue.run_repeating(check_job_status, interval=10, first=5, context=(user_id, job_id))

            else:
                for match in result:
                    with open("./Dataset/"+match['photo_path'], 'rb') as photo_file:
                        update.message.reply_photo(photo_file)
                
                update.message.reply_text(f"Search complete. Total matches found: {len(result)} \n"
                                        f"Total images processed: {job_data['total_images']}\n"
                                        f"What would you like to do next?")
                delete_job_entry(job_id)

            
        elif update.message.text in ['/n', 'n', '/N', 'N', 'no', 'No', 'NO']:
            find_id = add_find_entry(job_data['user_id'], job_data['photo_filename'], job_data['total_images'])
            update_job_entry(job_id, {'status': 'pending', 'search': True, 'find_id': find_id})
            update.message.reply_text("Okay, we'll continue searching with the provided image.")
            # restart the job
            context.job_queue.run_repeating(check_job_status, interval=10, first=5, context=(user_id, job_id))
        else:
            update.message.reply_text("Invalid input. Please type /Y for Yes or /N for No.")
            return



def check_job_status(context: CallbackContext):
    job = context.job
    user_id, job_id = job.context
    job_data = read_job_entry(job_id)
    
    if job_data:
        if job_data['status'] == 'completed':
            # Check for new matches
            conn = get_db_connection()
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            cur.execute('SELECT id, photo_path FROM found_photos WHERE find_id = ? AND id > ?', 
                        (job_data['find_id'], job_data['last_sent_match_id']))
            new_matches = cur.fetchall()
            
            for match in new_matches:
                with open("./Dataset/"+match['photo_path'], 'rb') as photo_file:
                    context.bot.send_photo(user_id, photo_file,
                                           f"Match found!\n")
            context.bot.send_message(user_id, f"Search complete. Total matches found: {job_data['match_count']}")
            context.bot.send_message(user_id, "What would you like to do next?")
            delete_job_entry(job_id)
            job.schedule_removal()
        elif job_data['status'] == 'error':
            context.bot.send_message(user_id, f"An error occurred while processing your request: {job_data.get('error_message', 'Unknown error')}")
            delete_job_entry(job_id)
            job.schedule_removal()
        elif job_data['status'] == 'Already_Processed' or job_data['status'] == 'Dataset_Incressed':
            context.bot.send_message(user_id, f"A similar image has already been processed before. \n"
                                     f"Is this the same person you're looking for? \n")
            conn = get_db_connection()
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            cur.execute('SELECT original_image FROM finds WHERE id = ?', (job_data['find_id'],))
            result = cur.fetchone()
            with open("./People/"+result['original_image'], 'rb') as photo_file:
                context.bot.send_photo(user_id, photo_file,
                                       f"Type 'Y' if Yes\n"
                                       f"Type 'N' if No\n")
            
            # Update job status to wait for user input
            update_job_entry(job_id, {'waiting_for_user': True})
            
            # Stop the job
            job.schedule_removal()

        elif job_data['status'] == 'processing':
            if job_data['Processing_message_sent'] == False:
                context.bot.send_message(
                    user_id,
                    f"Processing your request.\n"
                    f"Total images to process: {job_data['total_images']}"
                )
                update_job_entry(job_id, {'Processing_message_sent': True})
            
            # Check for new matches
            conn = get_db_connection()
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            cur.execute('SELECT id, photo_path FROM found_photos WHERE find_id = ? AND id > ?', 
                        (job_data['find_id'], job_data['last_sent_match_id']))
            new_matches = cur.fetchall()
            
            for match in new_matches:
                with open("./Dataset/"+match['photo_path'], 'rb') as photo_file:
                    context.bot.send_photo(user_id, photo_file,
                                           f"Match found!\n") 
            update_job_entry(job_id,{'last_sent_match_id': new_matches[-1]['id']})
            context.bot.send_message(
                    user_id,
                    f"Current match count: {job_data['match_count']}\n"
                    f"Images processed: {job_data['images_processed']}"
                )
            conn.close()
        else:
            context.bot.send_message(user_id, "Your request is in queue.")
    else:
        job.schedule_removal()