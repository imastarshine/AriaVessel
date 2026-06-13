from telebot.states import StatesGroup, State


class UserSteps(StatesGroup):
    waiting_for_setting_int_value = State()
    waiting_for_setting_str_value = State()
