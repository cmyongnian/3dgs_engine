from core.train_service import TrainerService


def main():
    trainer = TrainerService()
    trainer.run()


if __name__ == "__main__":
    main()