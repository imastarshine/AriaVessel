import src.bot
import src.bot.actions
import src.bot.informant
import src.bot.receiver
import src.bot.security
import src.bot.settings
import src.bot.shared
import src.bot.states
import src.bot.upload

# TODO: Move all descriptions for commands to here
def initialize():

    # informant.py
    src.bot.bot.register_message_handler(
        src.bot.security.restricted(src.bot.informant.start_command),
        commands=['start']
    )
    src.bot.bot.register_message_handler(
        src.bot.security.restricted(src.bot.informant.status_command),
        commands=['status']
    )
    src.bot.bot.register_message_handler(
        src.bot.security.restricted(src.bot.informant.inspect_command),
        commands=['inspect']
    )

    # actions.py
    src.bot.bot.register_message_handler(
        src.bot.security.restricted(src.bot.actions.control_command),
        commands=['pause', 'resume', 'rm', 'del']
    )

    # settings.py
    src.bot.bot.register_message_handler(
        src.bot.security.restricted(src.bot.settings.settings_command),
        commands=['settings']
    )

    src.bot.bot.register_message_handler(
        src.bot.settings.set_int_config_item,
        state=src.bot.states.UserSteps.waiting_for_setting_int_value
    )

    src.bot.bot.register_message_handler(
        src.bot.settings.set_str_config_item,
        state=src.bot.states.UserSteps.waiting_for_setting_str_value
    )

    src.bot.bot.register_callback_query_handler(
        src.bot.security.restricted(src.bot.settings.process_settings_callback),
        func=lambda call: call.data.startswith("e:")
    )

    # upload.py
    src.bot.bot.register_message_handler(
        src.bot.security.restricted(src.bot.upload.upload_command),
        commands=['upload']
    )

    src.bot.bot.register_message_handler(
        src.bot.security.restricted(src.bot.upload.upload_status_command),
        commands=['upload_status']
    )

    src.bot.bot.register_message_handler(
        src.bot.security.restricted(src.bot.upload.upload_cancel_command),
        commands=['upload_cancel']
    )

    # receiver.py
    src.bot.bot.register_message_handler(
        src.bot.security.restricted(src.bot.receiver.after_command),
        commands=['after']
    )

    src.bot.bot.register_message_handler(
        src.bot.security.restricted(src.bot.receiver.handle_source),
        content_types=["document", "text"]
    )

    src.bot.bot.register_callback_query_handler(
        src.bot.security.restricted(src.bot.receiver.confirm_callback),
        func=lambda call: call.data.startswith("confirm_")
    )
