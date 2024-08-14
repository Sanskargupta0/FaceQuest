import logging
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, ConversationHandler
from handlers import start, find, receive_name, receive_selfie, upload, receive_dataset_image, cancel, global_message_handler
from config import TOKEN, CONVERSATION_STATES
from database import init_db
from utils import setup_directories

# Set up logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

def main():
    try:
        # Set up directories and database
        setup_directories()
        init_db()
        
        updater = Updater(TOKEN, use_context=True)
        dp = updater.dispatcher

        conv_handler = ConversationHandler(
            entry_points=[CommandHandler(['1', 'find'], find), CommandHandler(['2', 'upload'], upload)],
            states={
                CONVERSATION_STATES['NAME']: [MessageHandler(Filters.text & ~Filters.command, receive_name)],
                CONVERSATION_STATES['SELFIE']: [MessageHandler(Filters.photo, receive_selfie)],
                CONVERSATION_STATES['DATASET']: [MessageHandler(Filters.photo | Filters.document | Filters.text, receive_dataset_image)],
            },
            fallbacks=[CommandHandler(['3', 'cancel'], cancel)],
        )

        dp.add_handler(CommandHandler("start", start))
        dp.add_handler(conv_handler)

        # Add the global message handler
        dp.add_handler(MessageHandler(Filters.text & ~Filters.command, global_message_handler))

        updater.start_polling()
        updater.idle()
    except Exception as e:
        logger.error(f"Critical error in main: {str(e)}")
        if updater.running:
            updater.stop()
        main()  # Restart the bot

if __name__ == "__main__":
    main()