class OverviewService:
    def __init__(self, repository):
        self.repository = repository

    def get(self, filters):
        return self.repository.overview(filters)

