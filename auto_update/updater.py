from utils import ConfigurationService, LoggingService, fetch_shenzhen_weather
from utils.util_thunder import fetch_thunder_alert

# Initialize services
logging_service = LoggingService()
config_service = ConfigurationService(logger=logging_service)


def main():
    try:
        weather_data = fetch_shenzhen_weather(logging_service)
    except Exception as e:
        logging_service.log_error("autoupdate.main", str(e))
        weather_data = None

    if not weather_data:
        logging_service.log_error("autoupdate.main", "Official weather data was empty.")
        weather_data = {}

    # A Shenzhen-source failure must not prevent the regional monitor from running.
    weather_data["THUNDER_ALERT_CONFIG"] = fetch_thunder_alert(
        config_service.get_value("THUNDER_MONITOR_CONFIG", {}), logging_service
    )

    # Keep all front-end weather blocks in sync from the official Shenzhen source.
    config_service.set_values(weather_data)


if __name__ == "__main__":
    main()
