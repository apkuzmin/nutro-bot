def calculate_bmr(gender, weight, height, age):
    if gender == "Парень":
        return 88.362 + (13.397 * weight) + (4.799 * height) - (5.677 * age)
    else:  # Девушка
        return 447.593 + (9.247 * weight) + (3.098 * height) - (4.330 * age)

def calculate_tdee(bmr, activity):
    from config import ACTIVITY_COEFFS
    return bmr * ACTIVITY_COEFFS[activity]

def adjust_calories(tdee, goal):
    if goal == "Снижение веса":
        return tdee * 0.85
    elif goal == "Набор массы":
        return tdee * 1.15
    return tdee  # Поддержание веса

def calculate_macros(calories, goal):
    from config import MACRO_RATIOS
    protein_ratio, fat_ratio, carb_ratio = MACRO_RATIOS[goal]
    protein = (calories * protein_ratio) / 4
    fat = (calories * fat_ratio) / 9
    carbs = (calories * carb_ratio) / 4
    return protein, fat, carbs