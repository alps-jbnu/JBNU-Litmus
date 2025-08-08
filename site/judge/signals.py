import errno
import os

from django.conf import settings
from django.contrib.sites.models import Site
from django.core.cache import cache
from django.core.cache.utils import make_template_fragment_key
from django.contrib.auth.models import User
from django.db import connections, transaction
from django.apps import apps
from django.db.models.signals import post_delete, post_save, pre_save, pre_delete
from django.dispatch import receiver

from .caching import finished_submission
# from .models import BlogPost, Comment, Contest, ContestSubmission, EFFECTIVE_MATH_ENGINES, Judge, Language, License, \
#     MiscConfig, Organization, Problem, Profile, Submission, WebAuthnCredential
from .models import BlogPost, Comment, Contest, ContestSubmission, EFFECTIVE_MATH_ENGINES, Judge, Language, License, \
    MiscConfig, Problem, Profile, Submission, WebAuthnCredential
from .models.LatestSubmission import LatestSubmission
from .models.submission import SubmissionSource
    

    


def get_pdf_path(basename):
    return os.path.join(settings.DMOJ_PDF_PROBLEM_CACHE, basename)


def unlink_if_exists(file):
    try:
        os.unlink(file)
    except OSError as e:
        if e.errno != errno.ENOENT:
            raise

# # 기본 DB에서 삭제 전, 백업 DB에 데이터 저장
# @receiver(pre_delete, sender=User)
# def backup_user_data(sender, instance, **kwargs):
#     with transaction.atomic(using='backup'):
#         # 유저 정보 백업
#         with connections['backup'].cursor() as cursor:
#             user_fields = [field.column for field in User._meta.fields]
#             user_values = [getattr(instance, field.name) for field in User._meta.fields]
#             insert_query = f'INSERT INTO {User._meta.db_table} ({", ".join(user_fields)}) VALUES ({", ".join(["%s"] * len(user_values))})'
#             cursor.execute(insert_query, user_values)
        
#         # 모든 모델 가져오기
#         models = apps.get_models()
        
#         # 외래 키 제약 조건 비활성화
#         with connections['backup'].cursor() as cursor:
#             cursor.execute('SET FOREIGN_KEY_CHECKS=0;')

#         # 데이터 삽입
#         for model in models:
#             # User 모델을 참조하는 모든 외래 키 필드를 찾기
#             for field in model._meta.get_fields():
#                 if field.is_relation and field.related_model == User:
#                     # 참조되는 객체들 가져오기
#                     related_objects = model.objects.filter(**{field.name: instance})

#                     # 백업 모델 인스턴스 생성
#                     for obj in related_objects:
#                         with connections['backup'].cursor() as cursor:
#                             fields = []
#                             values = []

#                             for model_field in model._meta.fields:
#                                 field_value = getattr(obj, model_field.name)

#                                 # 외래 키 필드인 경우 ID 값을 사용
#                                 if model_field.is_relation:
#                                     field_value = getattr(field_value, 'id', field_value)

#                                 fields.append(model_field.column)
#                                 values.append(field_value)

#                             insert_query = f'INSERT INTO {model._meta.db_table} ({", ".join(fields)}) VALUES ({", ".join(["%s"] * len(values))})'
#                             cursor.execute(insert_query, values)

#         # 외래 키 제약 조건 활성화
#         with connections['backup'].cursor() as cursor:
#             cursor.execute('SET FOREIGN_KEY_CHECKS=1;')

@receiver(post_save, sender=Problem)
def problem_update(sender, instance, **kwargs):
    if hasattr(instance, '_updating_stats_only'):
        return

    cache.delete_many([
        make_template_fragment_key('submission_problem', (instance.id,)),
        make_template_fragment_key('problem_feed', (instance.id,)),
        'problem_tls:%s' % instance.id, 'problem_mls:%s' % instance.id,
    ])
    cache.delete_many([make_template_fragment_key('problem_html', (instance.id, engine, lang))
                       for lang, _ in settings.LANGUAGES for engine in EFFECTIVE_MATH_ENGINES])
    cache.delete_many([make_template_fragment_key('problem_authors', (instance.id, lang))
                       for lang, _ in settings.LANGUAGES])
    cache.delete_many(['generated-meta-problem:%s:%d' % (lang, instance.id) for lang, _ in settings.LANGUAGES])

    for lang, _ in settings.LANGUAGES:
        unlink_if_exists(get_pdf_path('%s.%s.pdf' % (instance.code, lang)))


@receiver(post_save, sender=Profile)
def profile_update(sender, instance, **kwargs):
    if hasattr(instance, '_updating_stats_only'):
        return

    # cache.delete_many([make_template_fragment_key('user_about', (instance.id, engine))
    #                    for engine in EFFECTIVE_MATH_ENGINES] +
    #                   [make_template_fragment_key('org_member_count', (org_id,))
    #                    for org_id in instance.organizations.values_list('id', flat=True)])
    cache.delete_many([make_template_fragment_key('user_about', (instance.id, engine))
                    for engine in EFFECTIVE_MATH_ENGINES])


@receiver(post_delete, sender=WebAuthnCredential)
def webauthn_delete(sender, instance, **kwargs):
    profile = instance.user
    if profile.webauthn_credentials.count() == 0:
        profile.is_webauthn_enabled = False
        profile.save(update_fields=['is_webauthn_enabled'])


@receiver(post_save, sender=Contest)
def contest_update(sender, instance, **kwargs):
    if hasattr(instance, '_updating_stats_only'):
        return

    cache.delete_many(['generated-meta-contest:%d' % instance.id] +
                      [make_template_fragment_key('contest_html', (instance.id, engine))
                       for engine in EFFECTIVE_MATH_ENGINES])


@receiver(post_save, sender=License)
def license_update(sender, instance, **kwargs):
    cache.delete(make_template_fragment_key('license_html', (instance.id,)))


@receiver(post_save, sender=Language)
def language_update(sender, instance, **kwargs):
    cache.delete_many([make_template_fragment_key('language_html', (instance.id,)),
                       'lang:cn_map'])


@receiver(post_save, sender=Judge)
def judge_update(sender, instance, **kwargs):
    cache.delete(make_template_fragment_key('judge_html', (instance.id,)))


@receiver(post_save, sender=Comment)
def comment_update(sender, instance, **kwargs):
    cache.delete('comment_feed:%d' % instance.id)


@receiver(post_save, sender=BlogPost)
def post_update(sender, instance, **kwargs):
    cache.delete_many([
        make_template_fragment_key('post_summary', (instance.id,)),
        'blog_slug:%d' % instance.id,
        'blog_feed:%d' % instance.id,
    ])
    cache.delete_many([make_template_fragment_key('post_content', (instance.id, engine))
                       for engine in EFFECTIVE_MATH_ENGINES])


@receiver(post_delete, sender=Submission)
def submission_delete(sender, instance, **kwargs):
    finished_submission(instance)
    instance.user._updating_stats_only = True
    instance.user.calculate_points()
    instance.problem._updating_stats_only = True
    instance.problem.update_stats()


@receiver(post_delete, sender=ContestSubmission)
def contest_submission_delete(sender, instance, **kwargs):
    participation = instance.participation
    participation.recompute_results()
    Submission.objects.filter(id=instance.submission_id).update(contest_object=None)


# @receiver(post_save, sender=Organization)
# def organization_update(sender, instance, **kwargs):
#     cache.delete_many([make_template_fragment_key('organization_html', (instance.id, engine))
#                        for engine in EFFECTIVE_MATH_ENGINES])


_misc_config_i18n = [code for code, _ in settings.LANGUAGES]
_misc_config_i18n.append('')


def misc_config_cache_delete(key):
    cache.delete_many(['misc_config:%s:%s:%s' % (domain, lang, key.split('.')[0])
                       for lang in _misc_config_i18n
                       for domain in Site.objects.values_list('domain', flat=True)])


@receiver(pre_save, sender=MiscConfig)
def misc_config_pre_save(sender, instance, **kwargs):
    try:
        old_key = MiscConfig.objects.filter(id=instance.id).values_list('key').get()[0]
    except MiscConfig.DoesNotExist:
        old_key = None
    instance._old_key = old_key


@receiver(post_save, sender=MiscConfig)
def misc_config_update(sender, instance, **kwargs):
    misc_config_cache_delete(instance.key)
    if instance._old_key is not None and instance._old_key != instance.key:
        misc_config_cache_delete(instance._old_key)


@receiver(post_delete, sender=MiscConfig)
def misc_config_delete(sender, instance, **kwargs):
    misc_config_cache_delete(instance.key)


@receiver(post_save, sender=ContestSubmission)
def contest_submission_update(sender, instance, **kwargs):
    # 제출에 해당하는 경진 과제/대회 ID를 업데이트하는 작업만 수행
    # 점수 재계산은 이미 Submission.update_contest에서 이루어지므로 여기서는 수행하지 않음
    Submission.objects.filter(id=instance.submission_id).update(contest_object_id=instance.participation.contest_id)


# 유저


@receiver(post_save, sender=Submission)
def update_latest_submission(sender, instance, created, **kwargs):
    """
    채점 완료 후 최신 제출 기록 갱신
    """
    print(" 시그널 호출됨: 제출 ID =", instance.id)

    # 점수가 아직 없다면 (채점 미완료), 무시
    if not instance.is_graded:
        print(" 아직 채점 전이므로 건너뜀")
        return

    try:
        source = instance.source.source  # OneToOneField로 연결됨
    except SubmissionSource.DoesNotExist:
        source = ""

    latest, created_latest = LatestSubmission.objects.get_or_create(
        user=instance.user.user,
        problem=instance.problem,
        contest_object=instance.contest_object,
        defaults={
            'source': source,
            'score': instance.points or 0.0,
        }
    )

    if not created_latest:
        prev_score = latest.score or 0.0
        new_score = instance.points or 0.0

        if new_score >= prev_score:
            latest.score = new_score
            latest.source = source
            latest.language=instance.language
            latest.save()
