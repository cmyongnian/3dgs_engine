from core.metrics_service import MetricsService


def main():
    metrics = MetricsService()
    metrics.run()


if __name__ == "__main__":
    main()