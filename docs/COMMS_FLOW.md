# COMMS Flow

Текущий `Telegram / owner` flow после декомпозиции:

## 1. `CommsAgent`
`CommsAgent` теперь координирует несколько явных lane-модулей вместо большого monolith-path.

Основные lanes:
- `comms_owner_control_lane`
- `comms_notification_router`
- `comms_broadcast_queue`
- `comms_message_preflight_lane`
- `comms_message_route_lane`
- `comms_service_lane`
- `comms_service_runtime_lane`
- `comms_runtime_auth_lane`
- `comms_auth_command_lane`
- `comms_preference_lane`
- `comms_planning_lane`
- `comms_goal_skill_lane`
- `comms_runtime_control_lane`
- `comms_operational_command_lane`
- `comms_startup_lane`
- `comms_attachment_lane`
- `comms_owner_command_lane`
- `comms_research_state_lane`
- `comms_core_runtime_lane`
- `comms_lifecycle_lane`

## 2. Message path
1. `_on_message`
2. preflight checks:
   - pending confirmations
   - pending auth
   - pending approvals
   - contextual service state
3. deterministic owner-route:
   - status / cancel / stop / continue
   - menu/buttons
   - auth/status/inventory
4. owner/control/task/goal/service lanes
5. fallback to `ConversationEngine`

## 3. `ConversationEngine`
`ConversationEngine` тоже разрезан на lanes:
- `conversation_intake_lane`
- `conversation_context_lane`
- `conversation_context_memory_lane`
- `conversation_quick_lane`
- `conversation_question_lane`
- `conversation_dialogue_lane`
- `conversation_guard_lane`
- `conversation_state_lane`
- `conversation_session_lane`
- `conversation_parse_lane`
- `conversation_owner_profile_lane`
- `conversation_deterministic_owner_lane`
- `conversation_action_lane`

## 4. Decision / execution
После conversational parse:
1. deterministic owner route, если команда уже известного типа;
2. иначе `ConversationEngine.process_message`;
3. при наличии actions -> `conversation_action_lane`;
4. тяжелые owner-actions в Telegram выполняются deferred/background path, чтобы первый ответ не блокировался.

## 5. Guarding
- `Final Verifier`
- platform quality gates
- owner-grade repeatability checks
- deterministic owner-control shortcuts
- protected object registry / task_root_id invariants

## 6. Current design rule
Новый функционал в `comms` и `conversation` нельзя добавлять обратно в megaclass напрямую.
Новые куски должны входить через отдельный lane/module с:
- thin wrapper в основном классе;
- `py_compile`;
- таргетный `pytest`;
- owner simulator regression.
