from utils import ConfigurationService, LoggingService, fetch_live_data, fetch_fallback_data

# Initialize services
logging_service = LoggingService()
config_service = ConfigurationService(logger=logging_service)


def main():
    try:
        live_data = fetch_live_data(logging_service)
        if live_data is None or not any(live_data.values()):
            logging_service.log_error("autoupdate.main", "Live data fetch failed, using fallback data.")
            live_data = fetch_fallback_data(logging_service)
    except Exception as e:
        logging_service.log_error("autoupdate.main", str(e))
        live_data = fetch_fallback_data(logging_service)

    # Update configuration with new data
    config_service.set_value("LIVE_DATA", live_data)


if __name__ == "__main__":
    main()
