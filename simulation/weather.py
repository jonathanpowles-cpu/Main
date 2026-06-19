import random
from models.enums import WeatherCondition


WEATHER_TRANSITIONS = {
    WeatherCondition.CLEAR: {
        WeatherCondition.CLEAR: 0.50,
        WeatherCondition.FAIR: 0.35,
        WeatherCondition.PARTLY_CLOUDY: 0.10,
        WeatherCondition.CLOUDY: 0.03,
        WeatherCondition.FOG: 0.02,
    },
    WeatherCondition.FAIR: {
        WeatherCondition.CLEAR: 0.25,
        WeatherCondition.FAIR: 0.40,
        WeatherCondition.PARTLY_CLOUDY: 0.25,
        WeatherCondition.CLOUDY: 0.08,
        WeatherCondition.FOG: 0.02,
    },
    WeatherCondition.PARTLY_CLOUDY: {
        WeatherCondition.CLEAR: 0.05,
        WeatherCondition.FAIR: 0.20,
        WeatherCondition.PARTLY_CLOUDY: 0.35,
        WeatherCondition.CLOUDY: 0.25,
        WeatherCondition.OVERCAST: 0.10,
        WeatherCondition.RAIN: 0.05,
    },
    WeatherCondition.CLOUDY: {
        WeatherCondition.FAIR: 0.05,
        WeatherCondition.PARTLY_CLOUDY: 0.15,
        WeatherCondition.CLOUDY: 0.35,
        WeatherCondition.OVERCAST: 0.25,
        WeatherCondition.RAIN: 0.15,
        WeatherCondition.STORM: 0.05,
    },
    WeatherCondition.OVERCAST: {
        WeatherCondition.PARTLY_CLOUDY: 0.05,
        WeatherCondition.CLOUDY: 0.20,
        WeatherCondition.OVERCAST: 0.35,
        WeatherCondition.RAIN: 0.30,
        WeatherCondition.STORM: 0.10,
    },
    WeatherCondition.RAIN: {
        WeatherCondition.CLOUDY: 0.10,
        WeatherCondition.OVERCAST: 0.25,
        WeatherCondition.RAIN: 0.40,
        WeatherCondition.STORM: 0.15,
        WeatherCondition.FOG: 0.10,
    },
    WeatherCondition.FOG: {
        WeatherCondition.CLEAR: 0.15,
        WeatherCondition.FAIR: 0.30,
        WeatherCondition.PARTLY_CLOUDY: 0.20,
        WeatherCondition.FOG: 0.30,
        WeatherCondition.CLOUDY: 0.05,
    },
    WeatherCondition.STORM: {
        WeatherCondition.OVERCAST: 0.15,
        WeatherCondition.RAIN: 0.35,
        WeatherCondition.STORM: 0.40,
        WeatherCondition.CLOUDY: 0.10,
    },
}

VISIBILITY_MAP = {
    WeatherCondition.CLEAR: 1.0,
    WeatherCondition.FAIR: 0.9,
    WeatherCondition.PARTLY_CLOUDY: 0.75,
    WeatherCondition.CLOUDY: 0.5,
    WeatherCondition.OVERCAST: 0.3,
    WeatherCondition.RAIN: 0.2,
    WeatherCondition.FOG: 0.1,
    WeatherCondition.STORM: 0.05,
}

FLYING_SUITABILITY = {
    WeatherCondition.CLEAR: 1.0,
    WeatherCondition.FAIR: 0.95,
    WeatherCondition.PARTLY_CLOUDY: 0.85,
    WeatherCondition.CLOUDY: 0.65,
    WeatherCondition.OVERCAST: 0.4,
    WeatherCondition.RAIN: 0.2,
    WeatherCondition.FOG: 0.05,
    WeatherCondition.STORM: 0.0,
}


def advance_weather(current: WeatherCondition) -> WeatherCondition:
    transitions = WEATHER_TRANSITIONS[current]
    roll = random.random()
    cumulative = 0.0
    for condition, probability in transitions.items():
        cumulative += probability
        if roll <= cumulative:
            return condition
    return current


def get_visibility(weather: WeatherCondition) -> float:
    return VISIBILITY_MAP.get(weather, 0.5)


def is_flyable(weather: WeatherCondition) -> bool:
    return FLYING_SUITABILITY.get(weather, 0.0) > 0.1


def bombing_accuracy_modifier(weather: WeatherCondition) -> float:
    return VISIBILITY_MAP.get(weather, 0.5)
