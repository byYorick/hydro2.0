/** Темы библиотеки знаний (агрономия субстрат / гидропоника), с внешними источниками. */

export type KnowledgeCategory = 'substrate' | 'hydroponics' | 'water' | 'general'

/** Вкладки верхнего уровня внутри «Библиотеки знаний» (логический порядок: от контекста → к практике → к таблицам). */
export type LibrarySectionId = 'intro' | 'solution' | 'substrate' | 'systems' | 'references'

export interface KnowledgeSource {
  label: string
  url: string
}

export interface KnowledgeTopic {
  id: string
  title: string
  category: KnowledgeCategory
  /** Раздел вложенной навигации библиотеки */
  librarySection: LibrarySectionId
  /** Порядок внутри раздела (меньше — выше) */
  sortOrder: number
  summary: string
  points: string[]
  sources: KnowledgeSource[]
}

export interface CropEcPhRow {
  cropRu: string
  cropEn: string
  ecRange: string
  phRange: string
}

export interface ExternalGuideLink {
  title: string
  organization: string
  url: string
  note: string
}

export const LIBRARY_SECTION_TABS: Array<{
  id: LibrarySectionId
  label: string
  hint: string
}> = [
  {
    id: 'intro',
    label: 'Обзор и Россия',
    hint: 'Как устроен российский корпус литературы и как читать источники',
  },
  {
    id: 'solution',
    label: 'Вода и раствор',
    hint: 'Качество воды, pH, EC, питание по отечественным ориентирам',
  },
  {
    id: 'substrate',
    label: 'Субстрат и полив',
    hint: 'Маты, сток, дренаж, влага и солевой баланс',
  },
  {
    id: 'systems',
    label: 'Системы и сравнение',
    hint: 'NFT, агрегатопоника, сравнение с грунтом',
  },
  {
    id: 'references',
    label: 'Справочники',
    hint: 'Таблицы культур и каталог ссылок (РФ и международные)',
  },
]

/** Обзорный текст для вкладки «Россия» (не дублирует карточки — задаёт контекст). */
export const RUSSIAN_SEGMENT_OVERVIEW = {
  title: 'Российский сегмент литературы',
  paragraphs: [
    'В РФ нет полного аналога западной сети county extension в одном портале: практические нормы распределены между учебниками и монографиями (в т.ч. оцифрованными на Bibliotekar.ru), статьями в открытых репозиториях (КиберЛенинка, Naukaru и др.), методическими материалами вузов и региональных Минсельхозов, а также отраслевыми публикациями производственников.',
    'Для промышленной эксплуатации гидропоники полезно опираться на связку: научная статья (условия опыта, климат, сорт) + учебный фрагмент с типовыми EC/pH для томатов в минеральной вате + международный extension-гайд как проверка здравого смысла по поливу и стоку.',
    'Ниже приведены проверяемые открытые ссылки. Фрагменты на Bibliotekar часто отражают школу тепличного овощеводства прошлых десятилетий — используйте их как исторический и методический контекст и сверяйте с актуальным сортом, оборудованием и анализом воды.',
  ],
}

export const KNOWLEDGE_TOPICS: KnowledgeTopic[] = [
  {
    id: 'ru-literature-ecosystem',
    title: 'Где искать нормы в РФ: типы источников',
    category: 'general',
    librarySection: 'intro',
    sortOrder: 10,
    summary:
      'Краткая карта российского корпуса: рецензируемые журналы (КиберЛенинка), сборники и учебные тексты (Bibliotekar), научно-популярные и отраслевые статьи (Naukaru), региональные новости Минсельхозов (мероприятия, НИИ).',
    points: [
      'КиберЛенинка — удобно для поиска по культуре («салат», «светокультура», «pH раствора») и цитирования конкретного опыта.',
      'Bibliotekar — часто даёт цельные главы по питанию томатов в матах и классификации гидропонных методов; проверяйте дату первоисточника на странице.',
      'Региональные сайты (областные Минсельхозы) полезны для кормовых/специализированных линий и локальных семинаров — не всегда про овощи для рынка свежей продукции.',
    ],
    sources: [
      {
        label: 'КиберЛенинка — поиск по «гидропоника» / «питательный раствор»',
        url: 'https://cyberleninka.ru/search?q=%D0%B3%D0%B8%D0%B4%D1%80%D0%BE%D0%BF%D0%BE%D0%BD%D0%B8%D0%BA%D0%B0',
      },
      {
        label: 'Минсельхоз Саратовской области — семинар по гидропонным зелёным кормам (пример регионального трека)',
        url: 'https://www.minagro.saratov.gov.ru/development/index.php?ELEMENT_ID=4258',
      },
    ],
  },
  {
    id: 'water-quality',
    title: 'Качество исходной воды',
    category: 'water',
    librarySection: 'solution',
    sortOrder: 10,
    summary:
      'Перед расчётом рецепта полезно сдать воду в лабораторию: pH, EC, щёлочность, основные ионы (Na, Cl, Ca, Mg, Fe, Mn и др.). Это определяет необходимость осмоса, коррекции и запас по EC под удобрения.',
    points: [
      'Слишком высокий фоновый EC или токсичные уровни отдельных ионов ограничивают «окно» для внесения солей.',
      'Растворённый кислород и температура воды связаны: при перегреве раствора снижается запас O₂, что критично для DWC и систем с постоянным контактом корней с водой.',
      'Щёлочность влияет на стабильность pH после внесения удобрений и кислот.',
    ],
    sources: [
      {
        label: 'University of Missouri Extension — Hydroponic Nutrient Solutions (G6984)',
        url: 'https://extension.missouri.edu/publications/g6984',
      },
    ],
  },
  {
    id: 'ph-nutrient-availability',
    title: 'pH раствора и доступность элементов',
    category: 'hydroponics',
    librarySection: 'solution',
    sortOrder: 20,
    summary:
      'В бессубстратных системах нет почвенного буфера: pH раствора напрямую влияет на химическую доступность макро- и микроэлементов. Держите диапазон в «рабочем коридоре» и измеряйте в одно и то же время суток.',
    points: [
      'Для большинства овощных культур в soilless часто ориентируются на pH раствора около 5.5–6.5 (уточняйте по культуре).',
      'Сначала выводите EC в целевой диапазон, затем подстраивайте pH — так проще избежать гонок между дозами кислоты и солей.',
      'В субстрате полезно смотреть не только подачу, но и pH стока (лечата): расхождение с подачей сигнализирует о буферности среды или накоплении солей.',
    ],
    sources: [
      {
        label: 'Oklahoma State University — Electrical Conductivity and pH Guide for Hydroponics',
        url: 'https://extension.okstate.edu/fact-sheets/electrical-conductivity-and-ph-guide-for-hydroponics.html',
      },
      {
        label: 'University of Missouri Extension — Hydroponic Nutrient Solutions (G6984)',
        url: 'https://extension.missouri.edu/publications/g6984',
      },
    ],
  },
  {
    id: 'ru-tomato-greenhouse-nutrition',
    title: 'Томат в защищённом грунте: ориентиры EC/pH (отечественный учебный контекст)',
    category: 'hydroponics',
    librarySection: 'solution',
    sortOrder: 30,
    summary:
      'В отечественной тепличной литературе часто приводят пофазные цели pH и EC раствора и дренажа для малообъёмной технологии; цифры привязаны к конкретной методике и оборудованию — используйте как ориентир, не как ГОСТ.',
    points: [
      'Для томата в малообъёмном выращивании типично удерживать pH раствора около 5.5 и наращивать EC по фазам; на пике плодоношения в источнике встречаются уровни порядка 2.8–4.2 мСм/см при контроле накопления солей в мате.',
      'Авторы подчёркивают риск роста pH дренажа выше ~6.2 и накопления солей в мате; допустимое превышение EC «почвенного» раствора над подаваемым обычно обсуждают в узком коридоре (в литературе — порядка +0.5 мСм/см — сверяйте с вашим субстратом и прибором).',
      'Жёсткая вода с высоким Na/Cl может быть непригодна без доочистки — пороговые ориентиры по ионам приведены в том же пласте учебных материалов.',
    ],
    sources: [
      {
        label: 'Bibliotekar — Питание тепличных растений (макро- и микроэлементы, томат, дренаж)',
        url: 'http://www.bibliotekar.ru/7-ovoschi/52.htm',
      },
      {
        label: 'Bibliotekar — Питательные растворы и корректировка (концентрации, сезонность N/K)',
        url: 'http://bibliotekar.ru/7-gidroponika/11.htm',
      },
    ],
  },
  {
    id: 'ru-lettuce-ec-ph-study',
    title: 'Салат (светокультура): поддержание pH и EC в рабочем цикле',
    category: 'hydroponics',
    librarySection: 'solution',
    sortOrder: 40,
    summary:
      'Российские исследования по салату под искусственным светом показывают, что коррекция pH (например, азотной кислотой) может сопровождаться дрейфом EC и требует протоколирования.',
    points: [
      'Для интенсивной вегетации в источнике приводят ориентиры EC порядка 1.5–2.5 мСм/см с вариациями по сезону выращивания (весна/лето vs осень/зима для листового салата).',
      'Рост pH раствора может быть связан с бикарбонатным фоном прикорневой зоны; выбор кислоты для коррекции влияет на безопасность для оборудования и соотношение анионов.',
    ],
    sources: [
      {
        label: 'КиберЛенинка — поддержание pH и EC в цикле светокультуры салата',
        url: 'https://cyberleninka.ru/article/n/podderzhanie-optimalnyh-znacheniy-kislotnosti-i-elektroprovodnosti-pitatelnogo-rastvora-v-rabochem-tsikle-svetokultury-salata',
      },
    ],
  },
  {
    id: 'ec-management-leachate',
    title: 'EC подачи, EC субстрата и лечат',
    category: 'substrate',
    librarySection: 'substrate',
    sortOrder: 10,
    summary:
      'В субстрате измеряют EC прикорневой зоны или стока. Сравнение EC подачи и лечата показывает, накапливаются ли соли (недостаточный полив / высокая концентрация) или происходит «разбавление».',
    points: [
      'В практике тепличных soilless ориентир: EC лечата не должен расходиться с EC подачи более чем примерно на ±1 единицу EC (mS/cm ≈ dS/m); сильный перегрев лечата относительно подачи — сигнал к увеличению дренажа или снижению EC.',
      'При экстремальном накоплении солей (несколько единиц выше подачи) может потребоваться промывка водой с последующим возвратом к скорректированному раствору — не оставляйте культуру на одной воде надолго без программы питания.',
      'Частота полива зависит от удержания влаги субстратом: «тяжёлые» среды могут требовать меньше событий в сутки, высокодренажные — больше коротких импульсов.',
    ],
    sources: [
      {
        label: 'UF IFAS — Water and Nutrient Management Guidelines (HS1274)',
        url: 'https://edis.ifas.ufl.edu/publication/HS1274',
      },
      {
        label: 'Nova Scotia Vegetable Blog — Looking at Leachate (EC, pH, volume)',
        url: 'https://www.novascotiavegetableblog.com/2022/05/looking-at-leachate-what-are-my-ec-ph.html',
      },
    ],
  },
  {
    id: 'substrate-types-cec',
    title: 'Субстраты: инертные и с CEC (кокос)',
    category: 'substrate',
    librarySection: 'substrate',
    sortOrder: 20,
    summary:
      'Минеральные субстраты (перлит, каменная вата) обычно инертны: весь рацион через фертигацию. Органические вроде кокоса имеют катионоёмкость — часть Ca/Mg/K удерживается и высвобождается иначе, чем в инертных средах.',
    points: [
      'Кокос часто требует промывки и буферизации Ca/Mg до высадки, чтобы избежать ранних дефицитов из обмена ионами на матрице.',
      'Каменная вата быстрее реагирует на смену расписания полива; по кокосу решения часто принимают по трендам за несколько дней.',
      'Целевой pH корневой зоны для многих овощей часто обсуждают в коридоре примерно 5.5–6.5; точная цель зависит от культуры и стадии.',
    ],
    sources: [
      {
        label: 'Alsultana — Greenhouse Fertilization (substrate vs hydro overview)',
        url: 'https://alsultanafert.com/greenhouse-fertilization/',
      },
      {
        label: 'Hydrobuilder Learn — Crop Steering (coco & rockwool)',
        url: 'https://learn.hydrobuilder.com/what-is-crop-steering-coco-rockwool/',
      },
    ],
  },
  {
    id: 'ru-mineral-wool-mat-ec',
    title: 'Минеральная вата: баланс EC мата и поливного раствора',
    category: 'substrate',
    librarySection: 'substrate',
    sortOrder: 30,
    summary:
      'В отечественных рекомендациях по малообъёмной гидропонике подчёркивают, что EC мата и раствора должны согласовываться: избыточный рост EC в мате снижает урожай, заниженный — влияет на окраску и лёжкость плодов.',
    points: [
      'Перед посадкой мат насыщают раствором с EC порядка 2.5–3.0 мСм/см; до выхода на шпалеру поддерживают, чтобы EC в мате не выходила за целевой коридор.',
      'Далее рабочий EC мата часто держат в более узком диапазоне (в источнике — порядка 2.3–2.7 мСм/см), корректируя концентрацию подачи.',
      'Ориентир «EC подачи и мата на одном уровне» означает дисциплину измерений: решения принимают по тренду, а не по одному замеру.',
    ],
    sources: [
      {
        label: 'Bibliotekar — электропроводность и pH раствора (маты)',
        url: 'http://bibliotekar.ru/7-ovoschi/71.htm',
      },
    ],
  },
  {
    id: 'irrigation-steering',
    title: 'Полив, VWC и «руление» вегой/генерой',
    category: 'substrate',
    librarySection: 'substrate',
    sortOrder: 40,
    summary:
      'В субстрате полив управляет не только водным режимом, но и накоплением солей в корневой зоне. Отслеживание VWC, dryback и EC стока помогает сознательно смещать баланс роста при стабильном климате.',
    points: [
      'Первый сток дня имеет смысл, когда транспирация уже «разогналась» — иначе интерпретация EC стока шумная.',
      'Доля стока (drain %) — инструмент, а не самоцель: сверяйте её с EC стока и целями по культуре.',
      'Ночной полив в овощной гидропонике/субстрате часто избыточен: низкая транспирация, риск охлаждения корней и качества плода (по данным для ряда культур в тепличных руководствах).',
    ],
    sources: [
      {
        label: 'Hydrobuilder Learn — Crop Steering (coco & rockwool)',
        url: 'https://learn.hydrobuilder.com/what-is-crop-steering-coco-rockwool/',
      },
      {
        label: 'UF IFAS — Water and Nutrient Management Guidelines (HS1274)',
        url: 'https://edis.ifas.ufl.edu/publication/HS1274',
      },
    ],
  },
  {
    id: 'hydro-vs-substrate',
    title: 'Гидропоника без субстрата vs субстрат',
    category: 'general',
    librarySection: 'systems',
    sortOrder: 10,
    summary:
      'В NFT, DWC, аэропонике корни соприкасаются с раствором напрямую — нет «буфера» объёма субстрата. В slug/bag системах объём субстрата сглаживает краткосрочные ошибки полива, но добавляет задержку в EC/pH и необходимость мониторинга стока.',
    points: [
      'В «чистой» водной системе критичны температура, аэрация и гигиена резервуара.',
      'В субстрате критичны равномерность эмиттеров, представительные точки замера стока и интерпретация лечата.',
      'Пересадка программы с одного субстрата на другой без коррекции частоты и EC часто приводит к дефицитам или ожогам по солям.',
    ],
    sources: [
      {
        label: 'Oklahoma State University — EC and pH Guide for Hydroponics',
        url: 'https://extension.okstate.edu/fact-sheets/electrical-conductivity-and-ph-guide-for-hydroponics.html',
      },
      {
        label: 'UF IFAS — Water and Nutrient Management Guidelines (HS1274)',
        url: 'https://edis.ifas.ufl.edu/publication/HS1274',
      },
    ],
  },
  {
    id: 'ru-hydroponic-methods',
    title: 'Классификация гидропонных методов (агрегатопоника, плёночные желоба и др.)',
    category: 'general',
    librarySection: 'systems',
    sortOrder: 20,
    summary:
      'В отечественной терминологии выделяют агрегатопонику (субстрат-носитель), водную культуру, аэропонику и др.; для промышленного тепличного овощеводства исторически подчёркивали роль агрегатопоники.',
    points: [
      'Различие методов — в способе снабжения корней воздухом, водой и ионами; от этого зависят риски корневой гипоксии и требования к циркуляции.',
      'Плёночные желоба с тонким слоем раствора и рециркуляцией насосом — пример инженерной реализации «водной культуры» в теплице.',
      'Управление включает мониторинг pH и электропроводности; при падении EC выполняют корректировку раствора, при подщелачивании в типичных схемах используют фосфорную кислоту, при излишнем подкислении — щёлочные формы (как в учебных схемах — проверяйте совместимость с вашими реагентами и CHESS).',
    ],
    sources: [
      {
        label: 'Bibliotekar — гидропонный метод, водная культура, классификация',
        url: 'http://www.bibliotekar.ru/7-ovoschi/34.htm',
      },
    ],
  },
  {
    id: 'ru-lettuce-hydro-vs-soil',
    title: 'Листовой салат: сравнение гидропоники и грунта (урожайность и экономика)',
    category: 'general',
    librarySection: 'systems',
    sortOrder: 30,
    summary:
      'Прикладное сравнение технологий на одной культуре полезно для обоснования инвестиций; конкретные цифры привязаны к условиям эксперимента.',
    points: [
      'В цитируемой работе отмечено преимущество гидропоники по урожайности и экономическим показателям относительно «грунтовой» технологии в рамках постановки опыта.',
      'Тезис об отсутствии почвенного носителя патогенов не отменяет гигиены воды и воздуха в закрытой системе — биологическая безопасность остаётся задачей производства.',
    ],
    sources: [
      {
        label: 'КиберЛенинка — агротехнологии листового салата на гидропонике и грунте',
        url: 'https://cyberleninka.ru/article/n/agrotehnologicheskie-osobennosti-vozdelyvaniya-listovogo-salata-na-gidroponike-i-grunte',
      },
    ],
  },
  {
    id: 'ru-hydro-seedlings-naukaru',
    title: 'Гидропоника для рассады и посадочного материала',
    category: 'general',
    librarySection: 'systems',
    sortOrder: 40,
    summary:
      'Обзорные работы на российских научных платформах описывают открытые и замкнутые контуры, потери раствора на дренаж и мотивацию рециркуляции.',
    points: [
      'Для промышленных установок обсуждают как разовый сброс части раствора после полива (в источнике — порядка 25–30% для снижения осаждения солей на субстрате), так и замкнутые системы с возвратом в бак.',
      'Замкнутый контур снижает расход воды и риск загрязнения почвенных вод при штатной эксплуатации.',
    ],
    sources: [
      {
        label: 'Naukaru — гидропоника как альтернатива выращивания посадочного материала',
        url: 'https://naukaru.ru/ru/nauka/article/36624/view',
      },
    ],
  },
]

/** Ориентиры EC (mS/cm) и pH по таблице Oklahoma State University Extension; для одной культуры в разных источниках встречаются разные коридоры — используйте как стартовую точку. */
export const CROP_EC_PH_REFERENCE: CropEcPhRow[] = [
  { cropRu: 'Салат листовой', cropEn: 'Lettuce', ecRange: '1.2–1.8', phRange: '6.0–7.0' },
  { cropRu: 'Томат', cropEn: 'Tomato', ecRange: '2.0–4.0', phRange: '6.0–6.5' },
  { cropRu: 'Огурец', cropEn: 'Cucumber', ecRange: '1.7–2.0', phRange: '5.0–5.5' },
  { cropRu: 'Перец', cropEn: 'Peppers', ecRange: '0.8–1.8', phRange: '5.5–6.0' },
  { cropRu: 'Клубника', cropEn: 'Strawberry', ecRange: '1.8–2.2', phRange: '6.0' },
  { cropRu: 'Базилик', cropEn: 'Basil', ecRange: '1.0–1.6', phRange: '5.5–6.0' },
  { cropRu: 'Шпинат', cropEn: 'Spinach', ecRange: '1.8–2.3', phRange: '6.0–7.0' },
  { cropRu: 'Баклажан', cropEn: 'Eggplant', ecRange: '2.5–3.5', phRange: '6.0' },
  { cropRu: 'Фасоль', cropEn: 'Bean', ecRange: '2.0–4.0', phRange: '6.0' },
  { cropRu: 'Брокколи', cropEn: 'Broccoli', ecRange: '2.8–3.5', phRange: '6.0–6.8' },
  { cropRu: 'Капуста', cropEn: 'Cabbage', ecRange: '2.5–3.0', phRange: '6.5–7.0' },
  { cropRu: 'Сельдерей', cropEn: 'Celery', ecRange: '1.8–2.4', phRange: '6.5' },
  { cropRu: 'Кале / кейл', cropEn: 'Kale', ecRange: '1.6–2.5', phRange: '5.5–6.8' },
  { cropRu: 'Руккола', cropEn: 'Arugula', ecRange: '0.8–1.4', phRange: '5.5–6.8' },
  { cropRu: 'Дыня / арбуз (родственные культуры)', cropEn: 'Melon / Watermelon', ecRange: '1.5–2.5', phRange: '5.5–6.0' },
]

export const CROP_TABLE_SOURCE: KnowledgeSource = {
  label: 'Oklahoma State University Extension — Electrical Conductivity and pH Guide for Hydroponics (таблица культур)',
  url: 'https://extension.okstate.edu/fact-sheets/electrical-conductivity-and-ph-guide-for-hydroponics.html',
}

export const AUTHORITATIVE_EXTERNAL_GUIDES: ExternalGuideLink[] = [
  {
    title: 'Hydroponic Nutrient Solutions',
    organization: 'University of Missouri Extension (G6984)',
    url: 'https://extension.missouri.edu/publications/g6984',
    note: 'Вода, pH, EC, щёлочность, кислород, практики мониторинга.',
  },
  {
    title: 'Electrical Conductivity and pH Guide for Hydroponics',
    organization: 'Oklahoma State University Extension',
    url: 'https://extension.okstate.edu/fact-sheets/electrical-conductivity-and-ph-guide-for-hydroponics.html',
    note: 'Базовые принципы soilless и таблица ориентиров EC/pH по культурам.',
  },
  {
    title: 'Water and Nutrient Management Guidelines for Greenhouse Hydroponic Vegetable Production',
    organization: 'University of Florida IFAS (HS1274)',
    url: 'https://edis.ifas.ufl.edu/publication/HS1274',
    note: 'Полив, лечат, EC подачи vs субстрата, накопление солей.',
  },
  {
    title: 'Nutrient and pH Chart for Hydroponic Fruits and Vegetables',
    organization: 'IGWorks (коммерческий справочник)',
    url: 'https://igworks.com/blogs/growing-guides/nutrient-and-ph-chart-for-growing-hydroponic-fruits-and-vegetables',
    note: 'Расширенная таблица; перекрёстная проверка с университетскими источниками.',
  },
]

/** Каталог открытых российских материалов (наука, учебные тексты, отраслевые статьи). */
export const AUTHORITATIVE_RUSSIAN_GUIDES: ExternalGuideLink[] = [
  {
    title: 'Питание тепличных растений (макро- и микроэлементы)',
    organization: 'Bibliotekar.ru (фрагмент учебного комплекса)',
    url: 'http://www.bibliotekar.ru/7-ovoschi/52.htm',
    note: 'Томат в матах, EC/pH раствора и дренажа, ионы в воде.',
  },
  {
    title: 'Электропроводность и pH раствора (минеральная вата)',
    organization: 'Bibliotekar.ru',
    url: 'http://bibliotekar.ru/7-ovoschi/71.htm',
    note: 'Связь EC мата и поливного раствора.',
  },
  {
    title: 'Гидропонный метод: классификация подходов',
    organization: 'Bibliotekar.ru',
    url: 'http://www.bibliotekar.ru/7-ovoschi/34.htm',
    note: 'Агрегатопоника, водная культура, инженерные схемы.',
  },
  {
    title: 'Питательные растворы и корректировка',
    organization: 'Bibliotekar.ru',
    url: 'http://bibliotekar.ru/7-gidroponika/11.htm',
    note: 'Осмоляльность, сезонная коррекция N/K, общие принципы.',
  },
  {
    title: 'Поддержание pH и EC в цикле светокультуры салата',
    organization: 'КиберЛенинка (рецензируемая публикация)',
    url: 'https://cyberleninka.ru/article/n/podderzhanie-optimalnyh-znacheniy-kislotnosti-i-elektroprovodnosti-pitatelnogo-rastvora-v-rabochem-tsikle-svetokultury-salata',
    note: 'LED-освещение, коррекция кислотой, динамика EC.',
  },
  {
    title: 'Листовой салат: гидропоника vs грунт',
    organization: 'КиберЛенинка',
    url: 'https://cyberleninka.ru/article/n/agrotehnologicheskie-osobennosti-vozdelyvaniya-listovogo-salata-na-gidroponike-i-grunte',
    note: 'Сравнение технологий, экономические показатели в рамках опыта.',
  },
  {
    title: 'Гидропоника и посадочный материал (открытые и замкнутые системы)',
    organization: 'Naukaru',
    url: 'https://naukaru.ru/ru/nauka/article/36624/view',
    note: 'Обзор режимов полива и рециркуляции.',
  },
  {
    title: 'Производственное планирование тепличных овощей. Освещение и питание',
    organization: 'Reshetnikov-in.com (отраслевая методическая статья)',
    url: 'https://reshetnikov-in.com/works/%D1%81%D1%82%D0%B0%D1%82%D1%8C%D0%B8/%D1%82%D0%B5%D0%BF%D0%BB%D0%B8%D1%87%D0%BD%D1%8B%D0%B9-%D0%B1%D0%B8%D0%B7%D0%BD%D0%B5%D1%81/%D0%BF%D0%BB%D0%B0%D0%BD%D0%B8%D1%80%D0%BE%D0%B2%D0%B0%D0%BD%D0%B8%D0%B5-%D1%82%D0%B5%D0%BF%D0%BB%D0%B8%D1%87%D0%BD%D0%BE%D0%B3%D0%BE-%D0%B2%D1%8B%D1%80%D0%B0%D1%89%D0%B8%D0%B2%D0%B0%D0%BD%D0%B8%D1%8F-%D0%BE%D1%81%D0%B2%D0%B5%D1%89%D0%B5%D0%BD%D0%B8%D0%B5-%D0%BF%D0%B8%D1%82%D0%B0%D0%BD%D0%B8%D0%B5.html',
    note: 'NFT, минеральная вата, расход раствора на этапах огурца и др.',
  },
]

export const KNOWLEDGE_CATEGORY_LABELS: Record<KnowledgeCategory | 'all', string> = {
  all: 'Все темы',
  general: 'Общее',
  substrate: 'Субстрат / фертигация',
  hydroponics: 'Гидропоника (раствор)',
  water: 'Вода и качество',
}

export function topicsForLibrarySection(section: LibrarySectionId): KnowledgeTopic[] {
  return KNOWLEDGE_TOPICS
    .filter(t => t.librarySection === section)
    .sort((a, b) => a.sortOrder - b.sortOrder)
}
