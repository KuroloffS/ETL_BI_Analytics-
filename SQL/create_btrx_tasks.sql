CREATE TABLE btrx.tasks (
    id SERIAL PRIMARY KEY, -- Уникальный идентификатор записи
    subordinate CHAR(1), -- Поле "subordinate"
    parent_id INT, -- Поле "parentId"
    title TEXT, -- Поле "title"
    description TEXT, -- Поле "description"
    multitask CHAR(1), -- Поле "multitask"
    stage_id INT, -- Поле "stageId"
    created_by INT, -- Поле "createdBy"
    responsibleid INT, -- Поле "responsibleId"
    created_date TIMESTAMP WITH TIME ZONE, -- Поле "createdDate"
    changed_date TIMESTAMP WITH TIME ZONE, -- Поле "changedDate"
    closed_date TIMESTAMP WITH TIME ZONE, -- Поле "closedDate"
    date_start TIMESTAMP WITH TIME ZONE, -- Поле "dateStart"
    changed_by INT, -- Поле "changedBy"
    status_changed_by INT, -- Поле "statusChangedBy"
    closed_by INT, -- Поле "closedBy"
    duration_fact INT, -- Поле "durationFact"
    time_estimate INT, -- Поле "timeEstimate"
    time_spent_in_logs INT, -- Поле "timeSpentInLogs"
    description_in_bbcode CHAR(1), -- Поле "descriptionInBbcode"
    status INT, -- Поле "status"
    duration_plan INT, -- Поле "durationPlan"
    groupid INT, -- Поле "groupId"
    auditors JSON, -- Поле "auditors" (массив)
    accomplices JSON, -- Поле "accomplices" (массив)
    "group_id" INT, -- Поле "group.id"
    "group_name" TEXT, -- Поле "group.name"
    "group_opened" BOOLEAN, -- Поле "group.opened"
    "group_members_count" INT, -- Поле "group.membersCount"
    "group_image" TEXT, -- Поле "group.image"
    "group_additional_data" JSON, -- Поле "group.additionalData" (массив)
    "creator_id" INT, -- Поле "creator.id"
    "creator_name" TEXT, -- Поле "creator.name"
    "creator_link" TEXT, -- Поле "creator.link"
    "creator_icon" TEXT, -- Поле "creator.icon"
    "creator_work_position" TEXT, -- Поле "creator.workPosition"
    "responsible_id" INT, -- Поле "responsible.id"
    "responsible_name" TEXT, -- Поле "responsible.name"
    "responsible_link" TEXT, -- Поле "responsible.link"
    "responsible_icon" TEXT, -- Поле "responsible.icon"
    "responsible_work_position" TEXT, -- Поле "responsible.workPosition"
    accomplices_data JSON, -- Поле "accomplicesData" (массив)
    auditors_data JSON, -- Поле "auditorsData" (массив)
    sub_status INT -- Поле "subStatus"
);

select * from btrx.tasks;



