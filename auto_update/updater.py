from utils import ConfigurationService, LoggingService, fetch_shenzhen_weather

# Initialize services
logging_service = LoggingService()
config_service = ConfigurationService(logger=logging_service)


def main():
    try:
        weather_data = fetch_shenzhen_weather(logging_service)
    except Exception as e:
        logging_service.log_error("autoupdate.main", str(e))
        return

    if not weather_data:
        logging_service.log_error("autoupdate.main", "Official weather data was empty.")
        return

    # Keep all front-end weather blocks in sync from the official Shenzhen source.
    config_service.set_values(weather_data)


if __name__ == "__main__":
    main()
