#ifndef LIST_H
#define LIST_H

#include <stddef.h>

/*
 * list.h - Doubly linked list implementation using GNU C extensions.
 *
 * 이 파일은 GNU 확장 기능(예: __typeof__와 compound statement)을 사용합니다.
 * 만약 다른 컴파일러를 사용한다면, 해당 기능이 지원되는지 확인해야 합니다.
 */

/* 기본적인 offsetof 매크로 */
#define offsetof(TYPE, MEMBER) ((size_t)&((TYPE *)0)->MEMBER)

/* container_of: 주어진 멤버의 포인터를 포함하는 구조체 포인터를 반환 */
#define container_of(ptr, type, member) ({                      \
        const __typeof__(((type *)0)->member) *__mptr = (ptr);    \
        (type *)((char *)__mptr - offsetof(type, member)); })

/* 리스트 독성 포인터 값 */
#define LIST_POISON1  ((void *)0x00100100)
#define LIST_POISON2  ((void *)0x00200200)

/* 이중 연결 리스트의 기본 구조체 */
struct list_head {
    struct list_head *next, *prev;
};

/* 초기화 매크로 */
#define LIST_HEAD_INIT(name) { &(name), &(name) }
#define LIST_HEAD(name) \
    struct list_head name = LIST_HEAD_INIT(name)
#define INIT_LIST_HEAD(ptr) do { \
    (ptr)->next = (ptr);         \
    (ptr)->prev = (ptr);         \
} while (0)

/* 내부에서 리스트에 원소를 추가하는 함수 */
static inline void __list_add(struct list_head *new,
                              struct list_head *prev,
                              struct list_head *next)
{
    next->prev = new;
    new->next = next;
    new->prev = prev;
    prev->next = new;
}

/* 리스트 맨 앞에 원소 추가 */
static inline void list_add(struct list_head *new, struct list_head *head)
{
    __list_add(new, head, head->next);
}

/* 리스트 맨 뒤에 원소 추가 */
static inline void list_add_tail(struct list_head *new, struct list_head *head)
{
    __list_add(new, head->prev, head);
}

/* 내부에서 리스트에서 원소를 제거하는 함수 */
static inline void __list_del(struct list_head *prev, struct list_head *next)
{
    next->prev = prev;
    prev->next = next;
}

/* 리스트에서 원소 제거 */
static inline void list_del(struct list_head *entry)
{
    __list_del(entry->prev, entry->next);
    entry->next = LIST_POISON1;
    entry->prev = LIST_POISON2;
}

/* 리스트에서 원소 제거 후 초기화 */
static inline void list_del_init(struct list_head *entry)
{
    __list_del(entry->prev, entry->next);
    INIT_LIST_HEAD(entry);
}

/* 리스트의 원소를 다른 리스트로 이동 */
static inline void list_move(struct list_head *list, struct list_head *head)
{
    __list_del(list->prev, list->next);
    list_add(list, head);
}

/* 리스트의 원소를 맨 뒤로 이동 */
static inline void list_move_tail(struct list_head *list, struct list_head *head)
{
    __list_del(list->prev, list->next);
    list_add_tail(list, head);
}

/* 리스트가 비었는지 확인 */
static inline int list_empty(const struct list_head *head)
{
    return head->next == head;
}

/* 특정 구조체의 멤버 포인터로부터 해당 구조체 포인터를 얻음 */
#define list_entry(ptr, type, member) \
    container_of(ptr, type, member)

/* 리스트 순회 매크로들 */
#define list_for_each(pos, head) \
    for (pos = (head)->next; pos != (head); pos = pos->next)

#define list_for_each_prev(pos, head) \
    for (pos = (head)->prev; pos != (head); pos = pos->prev)

#define list_for_each_safe(pos, n, head) \
    for (pos = (head)->next, n = pos->next; pos != (head); \
         pos = n, n = pos->next)

/* 특정 구조체 타입을 포함하는 리스트를 순회 */
#define list_for_each_entry(pos, head, member)                         \
    for (pos = list_entry((head)->next, __typeof__(*pos), member);       \
         &pos->member != (head);                                         \
         pos = list_entry(pos->member.next, __typeof__(*pos), member))

#define list_for_each_entry_reverse(pos, head, member)                 \
    for (pos = list_entry((head)->prev, __typeof__(*pos), member);       \
         &pos->member != (head);                                         \
         pos = list_entry(pos->member.prev, __typeof__(*pos), member))

#define list_for_each_entry_safe(pos, n, head, member)                   \
    for (pos = list_entry((head)->next, __typeof__(*pos), member),         \
         n = list_entry(pos->member.next, __typeof__(*pos), member);        \
         &pos->member != (head);                                           \
         pos = n, n = list_entry(n->member.next, __typeof__(*n), member))

#define list_for_each_entry_safe_reverse(pos, n, head, member)           \
    for (pos = list_entry((head)->prev, __typeof__(*pos), member),         \
         n = list_entry(pos->member.prev, __typeof__(*pos), member);        \
         &pos->member != (head);                                           \
         pos = n, n = list_entry(n->member.prev, __typeof__(*n), member))

#endif /* LIST_H */
