from django.core.management.commands.migrate import Command as MigrateCommand
from django.core.management import call_command
from django.db import ProgrammingError, connections
from django.db.utils import OperationalError

class Command(MigrateCommand):
    help = '기본 및 백업 데이터베이스에 동일한 마이그레이션을 적용합니다.'

    def handle(self, *args, **kwargs):
        super().handle(*args, **kwargs)  # 기본 데이터베이스에 마이그레이션 적용

        # 백업 데이터베이스에 마이그레이션 적용
        self.stdout.write('Applying migrations to backup database...')
        
        try:
            # 백업 데이터베이스 연결 확인
            connections['backup'].ensure_connection()
        except OperationalError as e:
            self.stderr.write(f"Database connection error: {e}")
            return

        try:
            # 백업 데이터베이스에 마이그레이션 적용
            call_command('migrate', database='backup')
            self.stdout.write(self.style.SUCCESS('Schema successfully synced to backup database.'))
        except Exception as e:
            self.stderr.write(f"Error syncing schema: {e}")
