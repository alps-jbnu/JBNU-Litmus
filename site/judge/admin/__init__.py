from django.contrib import admin
from django.contrib.admin.models import LogEntry
from django.contrib.flatpages.models import FlatPage
from django.contrib.auth.models import User

from judge.admin.comments import CommentAdmin
from judge.admin.contest import ContestAdmin, ContestParticipationAdmin, ContestTagAdmin
from judge.admin.interface import BlogPostAdmin, FlatPageAdmin, LicenseAdmin, LogEntryAdmin, NavigationBarAdmin
# from judge.admin.organization import ClassAdmin, OrganizationAdmin, OrganizationRequestAdmin
from judge.admin.problem import ProblemAdmin, ProblemPointsVoteAdmin
from judge.admin.profile import ProfileAdmin, DepartmentAdmin, SubjectAdmin
from judge.admin.users import UserAdmin
from judge.admin.runtime import JudgeAdmin, LanguageAdmin
from judge.admin.submission import SubmissionAdmin
from judge.admin.taxon import ProblemGroupAdmin, ProblemTypeAdmin
from judge.admin.ticket import TicketAdmin
from judge.admin.patch_note import PatchNoteAdmin
# from judge.models import BlogPost, Class, Comment, CommentLock, Contest, ContestParticipation, \
#     ContestTag, Judge, Language, License, MiscConfig, NavigationBar, Organization, \
#     OrganizationRequest, Problem, ProblemGroup, ProblemPointsVote, ProblemType, Profile, Submission, Ticket


from judge.models import BlogPost, Comment, CommentLock, Contest, ContestParticipation, \
    ContestTag, Judge, Language, License, MiscConfig, NavigationBar, \
    Problem, ProblemGroup, ProblemPointsVote, ProblemType, Profile, Submission, Ticket, Department, Subject, \
    PatchNote

# admin.site.register(BlogPost, BlogPostAdmin)``
# admin.site.register(Comment, CommentAdmin) # 260112 댓글 기능 비활성화
# admin.site.register(CommentLock)
admin.site.register(Contest, ContestAdmin)
admin.site.register(ContestParticipation, ContestParticipationAdmin)
# admin.site.register(ContestTag, ContestTagAdmin)
admin.site.unregister(FlatPage)
# admin.site.register(FlatPage, FlatPageAdmin)
admin.site.register(Judge, JudgeAdmin)
admin.site.register(Language, LanguageAdmin)
admin.site.register(License, LicenseAdmin)
admin.site.register(LogEntry, LogEntryAdmin)
# admin.site.register(MiscConfig) # 기타 설정
admin.site.register(NavigationBar, NavigationBarAdmin)
# admin.site.register(Class, ClassAdmin)
# admin.site.register(Organization, OrganizationAdmin)
# admin.site.register(OrganizationRequest, OrganizationRequestAdmin)
admin.site.register(Problem, ProblemAdmin)
admin.site.register(ProblemGroup, ProblemGroupAdmin)
# admin.site.register(ProblemPointsVote, ProblemPointsVoteAdmin)
admin.site.register(ProblemType, ProblemTypeAdmin)
admin.site.register(Profile, ProfileAdmin)
admin.site.register(Department,DepartmentAdmin)
admin.site.register(Subject,SubjectAdmin)
admin.site.register(Submission, SubmissionAdmin)
admin.site.register(Ticket, TicketAdmin)

#유저가 생성될때, 프로필도 같이 생성
admin.site.unregister(User)
admin.site.register(User, UserAdmin)