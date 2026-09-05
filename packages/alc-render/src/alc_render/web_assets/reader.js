(function () {
  "use strict";

  var FRONT_BEGIN = "<!-- ALC:FRAGMENT-JSON:BEGIN -->";
  var FRONT_END = "<!-- ALC:FRAGMENT-JSON:END -->";
  var FRAGMENT_SCHEMA = "alc.render.fragment_revision.v3";
  var GLOSSARY_REVISION_SCHEMA = "alc.render.glossary_revision.v1";
  var GLOSSARY_MENTIONS_SCHEMA = "alc.render.glossary_mentions.v1";
  var GLOSSARY_PROPAGATION_SCHEMA = "alc.render.glossary_propagation.v1";
  var GLOSSARY_PROPAGATION_ROLES = ["translation", "companion", "guide"];
  var GLOSSARY_FRONT_BEGIN = "<!-- ALC:GLOSSARY-JSON:BEGIN -->";
  var GLOSSARY_FRONT_END = "<!-- ALC:GLOSSARY-JSON:END -->";
  var HEX_COLOR = /^#[0-9a-fA-F]{6}$/;
  var COLOR_PRESETS = [
    {name: "Ink", foreground: "#f9fafb", background: "#111827"},
    {name: "Paper", foreground: "#3a2e1f", background: "#fff4d6"},
    {name: "Ocean", foreground: "#17324d", background: "#e7f0fa"},
    {name: "Sage", foreground: "#193d2d", background: "#e7f1e9"},
    {name: "Plum", foreground: "#442857", background: "#f2eaf6"},
    {name: "Rose", foreground: "#572633", background: "#fbeaec"}
  ];
  var ROLE_APPEARANCES = {
    translation: {foreground: "#20262e", background: "#eaf1f8"},
    companion: {foreground: "#46515b", background: "#fffcf5"},
    guide: {foreground: "#46515b", background: "#fffcf5"},
    note: {foreground: "#f9fafb", background: "#111827"}
  };
  var READER_FONT_STACKS = {
    system: 'Inter, ui-sans-serif, system-ui, "PingFang SC", "Noto Sans CJK SC", sans-serif',
    arial: 'Arial, "Helvetica Neue", Helvetica, ui-sans-serif, sans-serif',
    helvetica: '"Helvetica Neue", Helvetica, Arial, ui-sans-serif, sans-serif',
    georgia: 'Georgia, "Times New Roman", Times, serif',
    times: '"Times New Roman", Times, serif',
    charter: 'Charter, "Iowan Old Style", "Source Serif 4", Georgia, serif',
    pingfang: '"PingFang SC", "Hiragino Sans GB", "Noto Sans CJK SC", sans-serif',
    heiti: '"Heiti SC", STHeiti, "Microsoft YaHei", "Noto Sans CJK SC", sans-serif',
    song: '"Songti SC", STSong, SimSun, "Noto Serif CJK SC", "Source Han Serif SC", serif',
    kai: '"Kaiti SC", STKaiti, KaiTi, serif'
  };
  var READER_PREFERENCE_DEFAULTS = {
    layout: "parallel",
    editActivation: "double",
    englishFont: "system",
    chineseFont: "system",
    scale: 100,
    lineHeight: 1.65,
    blockSpacing: 100,
    width: 100
  };
  var customSelectRegistry = new WeakMap();
  var customSelectSerial = 0;
  var MAX_BLOCKS_PER_RENDER_CHUNK = 36;
  var CHUNK_BLOCK_HEIGHT_ESTIMATE = 220;
  var DIRECTORY_READ_CONCURRENCY = 8;
  var STATUS_EXPIRY_MS = 3000;
  var state = {
    payload: null,
    payloadVersion: "v1",
    payloadChunks: [],
    payloadChunksById: new Map(),
    payloadChunkByBlockId: new Map(),
    loadedPayloadChunkIds: new Set(),
    loadingPayloadChunkIds: new Set(),
    md: null,
    revisions: new Map(),
    revisionDigests: new Map(),
    selected: new Map(),
    embeddedRevisions: [],
    activeFragmentIds: new Set(),
    diagnostics: [],
    fileDiagnostics: [],
    resolutionDiagnostics: new Map(),
    directory: null,
    directoryCacheHandle: null,
    directoryFileCache: new Map(),
    directoryLoadGeneration: 0,
    directorySelectionInProgress: false,
    glossaryDirectoryCacheHandle: null,
    glossaryFileCache: new Map(),
    saveInProgress: false,
    exportInProgress: false,
    exportMarkdownRoles: null,
    exportMarkdownKnownRoles: new Set(),
    activeDraft: null,
    editorGeneration: 0,
    editorPreviewDirty: true,
    editorPreviewTimer: null,
    statusTimer: null,
    editorBase: null,
    editorAnchor: null,
    editorHistorical: null,
    bibliographyIndexCache: null,
    sourceBibliographyIndex: {
      blockId: "", blockIds: new Set(), aliases: new Map(),
      itemIndexes: new Set(), itemIndexesByBlockId: new Map()
    },
    sourceStructuralIndex: {aliases: new Map(), blockIds: new Set()},
    sourceNoteIndex: {aliases: new Map(), targetIds: new Set()},
    sourceInternalLinkIndex: {aliases: new Map(), targetIds: new Set()},
    glossarySurfaceCache: {source: null, target: null},
    glossaryBase: [],
    glossaryDuplicateIds: new Set(),
    embeddedGlossaryRevisions: [],
    glossaryBaseDigests: new Map(),
    glossaryRevisions: new Map(),
    glossaryRevisionDigests: new Map(),
    selectedGlossary: new Map(),
    selectedGlossaryRevisions: new Map(),
    initialGlossaryDigests: new Map(),
    glossaryDiagnostics: [],
    glossaryFileDiagnostics: [],
    activeGlossaryDraft: null,
    editorKind: "fragment",
    indexedPayload: null,
    sourceIndexes: null,
    sourceIdentityJson: null,
    sourceIdentityValidatedPayload: null,
    fragmentGroups: new Map(),
    renderPlan: [],
    renderedChunkIds: new Set(),
    chunkNodes: new Map(),
    chunkByTargetId: new Map(),
    chunkObserver: null,
    idleRenderHandle: null,
    idleRenderUsesCallback: false,
    idleRenderGeneration: 0,
    hydrationQuietTimer: null,
    hydrationActivityReady: false,
    hydrationOrder: [],
    tableSyncScheduled: false,
    hashCalibration: null,
    diagnosticsRoot: null,
    readerShellReady: false,
    navigationReady: false,
    printReady: false,
    initialSelectedDigests: new Map(),
    initialSelectionCaptured: false,
    exportHtmlTemplate: null,
    exportStandaloneSupported: false,
    sourceVisible: true,
    pageMarkersVisible: false,
    hiddenRoles: new Set(),
    roleOrder: [],
    roleSlots: new Map(),
    appearanceGroups: new Map(),
    appearanceStyle: null,
    visibilityStyle: null,
    visibilityContentsSignature: null,
    visibilityReady: false,
    visibilityEmptyRoot: null,
    primaryTitleBlockId: "",
    primaryTitleFragmentId: "",
    readerPreferences: Object.assign({}, READER_PREFERENCE_DEFAULTS),
    readerSettingsReady: false,
    pendingReaderLinkTimer: null,
    pendingReaderLinkHref: "",
    speechSupported: false,
    speechReady: false,
    speechVoices: [],
    speechVoiceIdentity: "",
    speechVoiceIdentities: {source: "", target: ""},
    speechRate: 1,
    speechLoopMode: "none",
    speechRoles: new Set(["source"]),
    speechQueue: [],
    speechIndex: -1,
    speechUtterance: null,
    speechPlaying: false,
    speechPaused: false,
    speechGeneration: 0,
    speechActiveNode: null,
    speechStatus: "",
    speechStatusError: false
  };

  function element(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined && text !== null) node.textContent = String(text);
    return node;
  }

  function setOptionalText(id, value) {
    try {
      var node = document.getElementById(id);
      if (node) node.textContent = value;
    } catch (_error) {
      /* Minimal test DOMs and older exported shells may omit optional labels. */
    }
  }

  function setOptionalHidden(selector, hidden) {
    try {
      var node = document.querySelector(selector);
      if (node) node.hidden = hidden;
    } catch (_error) {
      /* Optional Fragment-only controls are absent from minimal shells. */
    }
  }

  function iconButton(className, symbol, accessibleLabel) {
    var button = element("button", className, symbol);
    button.type = "button";
    button.setAttribute("aria-label", accessibleLabel);
    button.title = accessibleLabel;
    return button;
  }

  function readPayload() {
    var node = document.getElementById("alc-render-payload");
    if (!node) throw new Error("ALC render payload is missing");
    var value = JSON.parse(node.textContent || "");
    if (!value || ![
      "alc.render.reader_payload.v1",
      "alc.render.reader_payload.v2"
    ].includes(value.schema_version)) {
      throw new Error("unsupported ALC reader payload");
    }
    if (!value.publication || !value.publication.source_document) {
      throw new Error("ALC reader payload has no source document");
    }
    state.payloadVersion = value.schema_version.endsWith(".v2") ? "v2" : "v1";
    state.payloadChunks = [];
    state.payloadChunksById = new Map();
    state.payloadChunkByBlockId = new Map();
    state.loadedPayloadChunkIds = new Set();
    state.loadingPayloadChunkIds = new Set();
    if (state.payloadVersion === "v2") {
      if (!Array.isArray(value.reader_chunks) || !Array.isArray(value.block_manifest)) {
        throw new Error("ALC reader payload has no chunk manifest");
      }
      state.payloadChunks = value.reader_chunks.slice();
      state.payloadChunksById = new Map(state.payloadChunks.map(function (item) {
        return [item.chunk_id, item];
      }));
      state.payloadChunks.forEach(function (descriptor) {
        for (var index = descriptor.block_start; index < descriptor.block_end; index += 1) {
          var block = value.block_manifest[index];
          if (block && block.block_id) {
            state.payloadChunkByBlockId.set(block.block_id, descriptor);
          }
        }
      });
      var blocks = value.publication.source_document.blocks;
      if (!Array.isArray(blocks) || blocks.length !== value.block_manifest.length) {
        throw new Error("ALC reader block manifest is inconsistent");
      }
      if (value.selected_roles !== undefined && !validSelectedRoles(value.selected_roles)) {
        throw new Error("ALC reader selected role manifest is invalid");
      }
      if (
        value.selected_heading_fragments !== undefined &&
        !validSelectedHeadingFragments(value.selected_heading_fragments)
      ) {
        throw new Error("ALC reader selected heading manifest is invalid");
      }
    }
    return value;
  }

  function validSelectedRoles(values) {
    if (!Array.isArray(values)) return false;
    var seen = new Set();
    return values.every(function (role) {
      if (!normalizedNonblank(role) || seen.has(role)) return false;
      seen.add(role);
      return true;
    });
  }

  function validSelectedHeadingFragments(values) {
    if (!Array.isArray(values)) return false;
    return values.every(function (item) {
      return item && normalizedNonblank(item.fragment_id) &&
        normalizedNonblank(item.role) && normalizedNonblank(item.target_id) &&
        Number.isFinite(Number(item.priority)) &&
        typeof item.markdown_body === "string";
    });
  }

  function loadPayloadChunk(descriptor) {
    if (
      !descriptor || state.loadedPayloadChunkIds.has(descriptor.chunk_id) ||
      state.loadingPayloadChunkIds.has(descriptor.chunk_id)
    ) return;
    var node = document.getElementById(descriptor.payload_id || "");
    if (!node) throw new Error("ALC reader chunk is missing: " + descriptor.chunk_id);
    var chunk = JSON.parse(node.textContent || "");
    if (
      !chunk || chunk.schema_version !== "alc.render.reader_chunk.v1" ||
      chunk.chunk_id !== descriptor.chunk_id ||
      chunk.block_start !== descriptor.block_start ||
      chunk.block_end !== descriptor.block_end ||
      !Array.isArray(chunk.blocks) ||
      chunk.blocks.length !== chunk.block_end - chunk.block_start ||
      !Array.isArray(chunk.revisions) ||
      (chunk.required_chunk_ids !== undefined &&
        !Array.isArray(chunk.required_chunk_ids))
    ) {
      throw new Error("ALC reader chunk is invalid: " + descriptor.chunk_id);
    }
    var documentBlocks = state.payload.publication.source_document.blocks;
    chunk.blocks.forEach(function (block, offset) {
      var index = chunk.block_start + offset;
      var manifest = state.payload.block_manifest[index];
      if (!manifest || manifest.block_id !== block.block_id) {
        throw new Error("ALC reader chunk block order is invalid");
      }
      documentBlocks[index] = block;
      ensureSourceIndexes().blocksById.set(block.block_id, block);
    });
    Object.keys(chunk.block_fingerprints || {}).forEach(function (blockId) {
      state.payload.block_fingerprints[blockId] =
        chunk.block_fingerprints[blockId];
    });
    state.loadingPayloadChunkIds.add(descriptor.chunk_id);
    try {
      payloadChunkDependencies(chunk, descriptor).forEach(function (chunkId) {
        var dependency = state.payloadChunksById.get(chunkId);
        if (!dependency || dependency === descriptor) {
          throw new Error("ALC reader chunk dependency is invalid");
        }
        loadPayloadChunk(dependency);
      });
      var fragmentIds = new Set();
      chunk.revisions.forEach(function (raw) {
        state.embeddedRevisions.push(raw);
        var metadata = raw.metadata || raw;
        if (metadata.fragment_id) {
          fragmentIds.add(metadata.fragment_id);
          state.activeFragmentIds.add(metadata.fragment_id);
        }
        addRevision(raw);
      });
      fragmentIds.forEach(function (fragmentId) {
        resolveFragmentInState(fragmentId, state.revisions.get(fragmentId) || []);
        if (state.readerShellReady) {
          var selected = state.selected.get(fragmentId);
          if (selected) updateFragmentGroup(fragmentId, selected.anchor);
        }
        if (state.initialSelectionCaptured) {
          var initial = state.selected.get(fragmentId);
          if (initial) {
            state.initialSelectedDigests.set(fragmentId, initial.semantic_digest);
          }
        }
      });
      syncAppearanceGroups();
      state.loadedPayloadChunkIds.add(descriptor.chunk_id);
      publishSelectedRevisionCount();
      rebuildDiagnostics();
      syncVisibilityRoles();
    } finally {
      state.loadingPayloadChunkIds.delete(descriptor.chunk_id);
    }
  }

  function payloadChunkDependencies(chunk, descriptor) {
    var declared = chunk.required_chunk_ids || [];
    var dependencies = new Set();
    declared.forEach(function (chunkId) {
      if (!normalizedNonblank(chunkId) || dependencies.has(chunkId)) {
        throw new Error("ALC reader chunk dependency is invalid");
      }
      dependencies.add(chunkId);
    });
    chunk.revisions.forEach(function (raw) {
      var metadata = raw.metadata || raw;
      var anchor = metadata.anchor || {};
      (anchor.related_blocks || []).forEach(function (frozen) {
        var dependency = state.payloadChunkByBlockId.get(frozen.block_id);
        if (dependency && dependency.chunk_id !== descriptor.chunk_id) {
          dependencies.add(dependency.chunk_id);
        }
      });
    });
    return Array.from(dependencies);
  }

  function publishSelectedRevisionCount() {
    if (typeof document !== "undefined" && document.body) {
      document.body.dataset.alcSelectedRevisionCount = String(state.selected.size);
    }
  }

  function loadPayloadForBlockRange(start, end) {
    if (state.payloadVersion !== "v2") return;
    state.payloadChunks.forEach(function (descriptor) {
      if (descriptor.block_end <= start || descriptor.block_start >= end) return;
      loadPayloadChunk(descriptor);
    });
  }

  function loadAllPayload(includeResources) {
    if (state.payloadVersion !== "v2") return;
    state.payloadChunks.forEach(loadPayloadChunk);
    if (includeResources) {
      (state.payload.resources || []).forEach(hydrateResource);
    }
  }

  function buildSourceIndexes() {
    var publication = state.payload.publication;
    var documentValue = publication.source_document;
    var blocksById = new Map();
    (documentValue.blocks || []).forEach(function (block) {
      blocksById.set(block.block_id, block);
    });
    var sectionsById = new Map();
    var sectionAnchors = new Map();
    (publication.outline || []).forEach(function (section) {
      sectionsById.set(section.section_id, section);
      sectionAnchors.set(section.section_id, section.anchor_block_id);
    });
    var resourcesByDigest = new Map();
    var resourcesByLogicalName = new Map();
    var resources = state.payload.resources || [];
    resources.forEach(function (resource) {
      var digest = resource.artifact_digest || resource.digest;
      if (digest) resourcesByDigest.set(digest, resource);
      if (resource.logical_name) {
        resourcesByLogicalName.set(resource.logical_name, resource);
      }
    });
    state.sourceIndexes = {
      blocksById: blocksById,
      sectionsById: sectionsById,
      sectionAnchors: sectionAnchors,
      resourcesByDigest: resourcesByDigest,
      resourcesByLogicalName: resourcesByLogicalName,
      resourceCount: resources.length
    };
    state.sourceIdentityJson = state.payload.source_identity ?
      stableStringify(state.payload.source_identity) : null;
    state.indexedPayload = state.payload;
  }

  function ensureSourceIndexes() {
    if (
      state.indexedPayload !== state.payload ||
      !state.sourceIndexes ||
      state.sourceIndexes.resourceCount !== (state.payload.resources || []).length
    ) {
      buildSourceIndexes();
    }
    return state.sourceIndexes;
  }

  function labels() {
    var publication = state.payload.publication;
    var language = targetLanguage().toLowerCase();
    var chinese = language === "zh" || language.indexOf("zh-") === 0;
    var traditional = chinese && /(?:^|-)hant(?:-|$)|(?:^|-)(?:tw|hk|mo)(?:-|$)/.test(
      language
    );
    var defaults = chinese ? {
      contents: "目录",
      collapse: "收起目录",
      expand: "展开目录",
      newSaveLocation: "新建保存位置",
      changeSaveLocation: "更改保存位置",
      connected: "保存位置已设置",
      edit: "编辑",
      addNote: "添加",
      editor: "编辑",
      newNote: "添加",
      title: "标题",
      role: "类型",
      priority: "优先级",
      colors: traditional ? "同類型與優先級的樣式" : "同类型与优先级的样式",
      foreground: traditional ? "字體顏色" : "字体颜色",
      background: traditional ? "背景顏色" : "背景颜色",
      roleDefaultColors: traditional ? "恢復類型預設" : "恢复类型默认",
      resizeContents: traditional ? "調整目錄寬度" : "调整目录宽度",
      advancedAction: "高级",
      markdown: "Markdown",
      preview: "预览",
      save: "保存",
      cancel: "取消",
      close: "关闭",
      deleteElement: "删除",
      deleteElementLabel: "删除此元素",
      deleteConfirm: "删除此元素？旧版本仍会保留。",
      deleteSuccess: "元素已删除。",
      history: "版本历史",
      source: "原文",
      translation: traditional ? "譯文" : "译文",
      companion: "伴读",
      guide: "导读",
      note: "笔记",
      glossary: "术语表",
      glossaryTerm: traditional ? "術語" : "术语",
      references: "参考文献",
      originalTerm: "原文术语",
      translatedTerm: traditional ? "譯文" : "译文",
      definition: "释义",
      glossaryDefinitionRecovered: traditional ?
        "原始釋義含損壞符號，已保留可恢復內容" :
        "原始释义含损坏符号，已保留可恢复内容",
      editGlossary: "编辑术语",
      glossaryEditor: "编辑术语",
      glossarySourceReadOnly: "原文（不可修改）",
      glossarySaveSuccess: "术语已保存为新版本。",
      glossarySaveUnchanged: "术语没有变化。",
      glossaryTranslatedRequired: "译文不能为空。",
      glossaryHistoryChanged: "目录中的术语版本已变化；请关闭编辑器并重新打开后再保存。",
      view: "显示",
      showLayers: "显示内容",
      original: "原文",
      authors: "作者",
      affiliations: traditional ? "作者單位" : "作者单位",
      orcid: "ORCID",
      sourceNote: traditional ? "腳註" : "脚注",
      sourceNoteBack: traditional ? "返回腳註標記" : "返回脚注标记",
      documentData: traditional ? "文件資料" : "文档数据",
      documentPage: traditional ? "文件頁" : "文档页",
      noVisibleContent: "未选择要显示的内容。",
      listen: traditional ? "朗讀" : "朗读",
      readContent: traditional ? "朗讀內容" : "朗读内容",
      voice: "声音",
      sourceVoice: "英文声音",
      targetVoice: "中文声音",
      automaticVoice: traditional ? "自動" : "自动",
      automaticVoiceSelection: traditional ?
        "自動（預設：{voice}）" : "自动（默认：{voice}）",
      localVoice: traditional ? "本機" : "本机",
      networkVoice: "联网",
      speechRate: "倍速",
      speechPlay: "播放",
      speechPause: "暂停",
      speechResume: "继续",
      speechStop: "停止",
      speechPrevious: "上一段",
      speechNext: "下一段",
      speechFromBeginning: "从头播放",
      speechPlaylist: "播放列表",
      speechLoopNone: "不循环",
      speechLoopAll: "全部循环",
      speechLoopOne: "单段循环",
      speechUnavailable: traditional ?
        "此瀏覽器不支援語音朗讀。" : "此浏览器不支持语音朗读。",
      speechNoVoices: traditional ?
        "未找到可用的系統聲音。請先在作業系統中安裝語音。" :
        "未找到可用的系统声音。请先在操作系统中安装语音。",
      speechChooseContent: traditional ?
        "請至少選擇一類朗讀內容。" : "请至少选择一类朗读内容。",
      speechNoReadableContent: traditional ?
        "所選類型沒有可朗讀的段落。" : "所选类型没有可朗读的段落。",
      speechReady: traditional ? "準備朗讀。" : "准备朗读。",
      speechFinished: traditional ? "朗讀完成。" : "朗读完成。",
      speechError: traditional ? "朗讀失敗：" : "朗读失败：",
      speechProgress: traditional ?
        "第 {current}/{total} 段" : "第 {current}/{total} 段",
      export: "导出",
      exportPanelHeading: "导出内容",
      markdownScope: "导出范围",
      markdownContent: "包含内容",
      markdownOutput: "输出方式",
      singleMarkdown: "单个 Markdown",
      markdownPackage: traditional ? "Markdown 套件" : "Markdown 包",
      allLatest: "全部",
      changedLatest: traditional ? "僅最新改動" : "仅最新改动",
      noExportChanges: "没有可导出的改动",
      selectExportContent: "请至少选择一项可导出的内容",
      fullMarkdown: traditional ?
        "导出Markdown" : "导出Markdown",
      exportMarkdownFile: "导出Markdown",
      htmlExport: "HTML",
      htmlExportDescription: "导出包含完整交互功能的单个阅读器文件。",
      fullHtml: "导出HTML",
      pdfExport: "PDF",
      pdfExportDescription: "打印当前显示的阅读器内容，也可在浏览器中保存为 PDF。",
      printPdf: "导出PDF",
      printOpened: "已打开打印对话框。",
      changedContent: "最新版改动",
      exportUnavailable: "当前页面不是完整的单文件阅读器，无法导出单个 HTML。",
      exportLoading: "正在同步最新版内容……",
      exportSyncFailed: "未能同步最新版内容，导出已取消。",
      exportStarted: "已开始导出。",
      revisionBusy: "正在保存或同步最新版内容，请稍候。",
      noDirectoryApi: "当前浏览器不支持本地目录编辑；阅读功能不受影响。",
      saveSuccess: "新版本已保存。",
      saveUnchanged: "内容没有变化。",
      draftActive: "请先保存或取消当前编辑。",
      draftRedirected: traditional ?
        "目前編輯有未儲存內容，已返回該編輯框。" :
        "当前编辑有未保存内容，已返回该编辑框。",
      saveCurrentChanges: "保存当前修改？",
      saveBeforeExit: traditional ?
        "你已修改目前內容，是否儲存？" : "你已修改当前内容，是否保存？",
      discardChanges: "不保存",
      saveChanges: "保存修改",
      continueEditing: "继续编辑",
      saveFailedInEditor: "未能完成保存。修改仍保留在编辑区，请检查页面提示后重试。",
      editContent: "编辑这段 Markdown",
      loading: "正在读取版本……",
      historyChanged: "目录中的当前版本已变化；请关闭编辑器并重新打开后再保存。",
      unknownCitation: "引用不在当前参考文献中：",
      referenceUnavailable: traditional ? "參考文獻連結不可用" : "参考文献链接不可用",
      scrollableTable: traditional ? "可水平捲動的表格" : "可横向滚动的表格",
      compareCurrent: "当前版本",
      compareHistorical: "历史版本",
      restore: "恢复为新版本",
      imageOmitted: "图片未加载",
      moreSettings: "更多设置",
      closeMoreSettings: "关闭更多设置",
      translationLayout: "译文布局",
      parallelLayout: "左右对照",
      stackedLayout: "上下对照",
      enterEditMode: "进入编辑",
      doubleClick: "双击",
      singleClick: "单击",
      englishFont: "英文字体",
      chineseFont: "中文字体",
      systemDefault: "系统默认",
      displayScale: "显示比例",
      readerLineHeight: traditional ? "行間距" : "行间距",
      readerBlockSpacing: traditional ? "段間距" : "段间距",
      contentWidth: "正文宽度",
      settingsNote: "设置仅影响当前预览，不修改源码。",
      restoreRecommended: "恢复推荐值"
    } : {
      contents: "Contents",
      collapse: "Collapse contents",
      expand: "Expand contents",
      newSaveLocation: "New save location",
      changeSaveLocation: "Change save location",
      connected: "Save location ready",
      edit: "Edit",
      addNote: "Add",
      editor: "Edit",
      newNote: "Add",
      title: "Title",
      role: "Role",
      priority: "Priority",
      colors: "Style for this role and priority",
      foreground: "Text color",
      background: "Background color",
      roleDefaultColors: "Use role default",
      resizeContents: "Resize contents",
      advancedAction: "Advanced",
      markdown: "Markdown",
      preview: "Preview",
      save: "Save",
      cancel: "Cancel",
      close: "Close",
      deleteElement: "Delete",
      deleteElementLabel: "Delete this element",
      deleteConfirm: "Delete this element? Earlier revisions will be retained.",
      deleteSuccess: "Element deleted.",
      history: "Revision history",
      source: "Source",
      translation: "Translation",
      companion: "Companion",
      guide: "Guide",
      note: "Note",
      glossary: "Glossary",
      glossaryTerm: "Glossary",
      references: "References",
      originalTerm: "Original term",
      translatedTerm: "Translation",
      definition: "Definition",
      glossaryDefinitionRecovered:
        "The original definition contained damaged symbols; recoverable content is shown",
      editGlossary: "Edit glossary term",
      glossaryEditor: "Edit glossary term",
      glossarySourceReadOnly: "Source (read-only)",
      glossarySaveSuccess: "Glossary term saved as a new revision.",
      glossarySaveUnchanged: "The glossary term is unchanged.",
      glossaryTranslatedRequired: "The translated term cannot be empty.",
      glossaryHistoryChanged: "The current directory glossary revision changed; close and reopen the editor before saving.",
      view: "View",
      showLayers: "Show content",
      original: "Original",
      authors: "Authors",
      affiliations: "Affiliations",
      orcid: "ORCID",
      sourceNote: "Footnote",
      sourceNoteBack: "Back to footnote reference",
      documentData: "Document data",
      documentPage: "Document page",
      noVisibleContent: "No content is selected for display.",
      listen: "Listen",
      readContent: "Read content",
      voice: "Voice",
      sourceVoice: "English voice",
      targetVoice: "Chinese voice",
      automaticVoice: "Automatic",
      automaticVoiceSelection: "Automatic (default: {voice})",
      localVoice: "local",
      networkVoice: "network",
      speechRate: "Rate",
      speechPlay: "Play",
      speechPause: "Pause",
      speechResume: "Resume",
      speechStop: "Stop",
      speechPrevious: "Previous paragraph",
      speechNext: "Next paragraph",
      speechFromBeginning: "Play from beginning",
      speechPlaylist: "Playlist",
      speechLoopNone: "No repeat",
      speechLoopAll: "Repeat all",
      speechLoopOne: "Repeat paragraph",
      speechUnavailable: "Speech is unavailable in this browser.",
      speechNoVoices: "No system voices were found. Install a voice in the operating system first.",
      speechChooseContent: "Select at least one content type to read.",
      speechNoReadableContent: "The selected content has no readable paragraphs.",
      speechReady: "Ready to read.",
      speechFinished: "Reading complete.",
      speechError: "Speech failed: ",
      speechProgress: "Paragraph {current} of {total}",
      export: "Export",
      exportPanelHeading: "Export content",
      markdownScope: "Export range",
      markdownContent: "Include",
      markdownOutput: "Output",
      singleMarkdown: "Single Markdown",
      markdownPackage: "Markdown package",
      allLatest: "All latest",
      changedLatest: "Latest changes only",
      noExportChanges: "No changed content to export",
      selectExportContent: "Select at least one available content type",
      fullMarkdown: "Export Markdown package",
      exportMarkdownFile: "Export Markdown",
      htmlExport: "HTML",
      htmlExportDescription: "Export the complete interactive Reader as one file.",
      fullHtml: "Export HTML",
      pdfExport: "PDF",
      pdfExportDescription: "Print the currently visible Reader, or save it as PDF in the browser.",
      printPdf: "Export PDF",
      printOpened: "Print dialog opened.",
      changedContent: "Latest changes",
      exportUnavailable: "This page is not a complete standalone reader and cannot export a single HTML file.",
      exportLoading: "Synchronizing latest content…",
      exportSyncFailed: "Latest content could not be synchronized; export was cancelled.",
      exportStarted: "Export started.",
      revisionBusy: "A save or latest-content sync is already in progress.",
      noDirectoryApi: "This browser cannot edit a local directory; reading is unaffected.",
      saveSuccess: "A new revision was saved.",
      saveUnchanged: "Content is unchanged.",
      draftActive: "Save or cancel the current edit first.",
      draftRedirected: "The current edit has unsaved changes; returned to it.",
      saveCurrentChanges: "Save current changes?",
      saveBeforeExit: "You changed the current content. Save it?",
      discardChanges: "Don't save",
      saveChanges: "Save changes",
      continueEditing: "Continue editing",
      saveFailedInEditor: "The save could not be completed. Changes remain in the editor; check the page status and try again.",
      editContent: "Edit this Markdown",
      loading: "Loading revisions…",
      historyChanged: "The current directory revision changed; close and reopen the editor before saving.",
      unknownCitation: "Citation is absent from the bibliography: ",
      referenceUnavailable: "Reference link unavailable",
      scrollableTable: "Scrollable table",
      compareCurrent: "Current revision",
      compareHistorical: "Historical revision",
      restore: "Restore as new revision",
      imageOmitted: "Image not loaded",
      moreSettings: "More settings",
      closeMoreSettings: "Close more settings",
      translationLayout: "Translation layout",
      parallelLayout: "Side by side",
      stackedLayout: "Stacked",
      enterEditMode: "Enter edit mode",
      doubleClick: "Double click",
      singleClick: "Single click",
      englishFont: "English font",
      chineseFont: "Chinese font",
      systemDefault: "System default",
      displayScale: "Display scale",
      readerLineHeight: "Line spacing",
      readerBlockSpacing: "Block spacing",
      contentWidth: "Content width",
      settingsNote: "Settings affect this preview only and do not modify source.",
      restoreRecommended: "Restore recommended values"
    };
    Object.keys(publication.labels || {}).forEach(function (key) {
      defaults[key] = publication.labels[key];
    });
    if (chinese && ["译名", "翻译", "譯名", "翻譯"].indexOf(defaults.translation) >= 0) {
      defaults.translation = traditional ? "譯文" : "译文";
    }
    if (chinese && ["译名", "翻译", "譯名", "翻譯"].indexOf(defaults.translatedTerm) >= 0) {
      defaults.translatedTerm = traditional ? "譯文" : "译文";
    }
    return defaults;
  }

  function targetLanguage() {
    var publication = state.payload && state.payload.publication || {};
    var profileLanguage = String(
      (publication.reader_profile || {}).target_language || ""
    ).trim();
    if (profileLanguage) return profileLanguage;
    var languages = new Set();
    if (state.selected instanceof Map) {
      state.selected.forEach(function (revision) {
        if (
          revision && revision.role === "translation" &&
          revision.deleted !== true && normalizedNonblank(revision.language)
        ) languages.add(String(revision.language).trim());
      });
    }
    return languages.size === 1 ? Array.from(languages)[0] : "";
  }

  function labelToolButton(button, label) {
    button.setAttribute("aria-label", label);
    button.title = label;
  }

  function positionToolPanel(panel) {
    if (
      !panel || panel.hidden || !panel.style ||
      typeof panel.getBoundingClientRect !== "function"
    ) return;
    var viewportWidth = document.documentElement.clientWidth || window.innerWidth;
    panel.style.maxWidth = Math.max(0, viewportWidth - 16) + "px";
    panel.style.transform = "";
    var rectangle = panel.getBoundingClientRect();
    var overflow = rectangle.right - (viewportWidth - 8);
    if (overflow > 0) {
      panel.style.transform = "translateX(-" + overflow + "px)";
    }
  }

  function boundedReaderNumber(value, fallback, minimum, maximum) {
    var number = Number(value);
    if (!Number.isFinite(number)) return fallback;
    return Math.min(maximum, Math.max(minimum, number));
  }

  function readerPreferenceSnapshot() {
    var data = document.body.dataset;
    var layout = data.alcReaderLayout;
    var activation = data.alcReaderEditActivation;
    var englishFont = data.alcReaderEnglishFont;
    var chineseFont = data.alcReaderChineseFont;
    return {
      layout: layout === "stacked" ? "stacked" : "parallel",
      editActivation: activation === "single" ? "single" : "double",
      englishFont: READER_FONT_STACKS[englishFont] ? englishFont : "system",
      chineseFont: READER_FONT_STACKS[chineseFont] ? chineseFont : "system",
      scale: boundedReaderNumber(
        data.alcReaderScale, READER_PREFERENCE_DEFAULTS.scale, 50, 150
      ),
      lineHeight: boundedReaderNumber(
        data.alcReaderLineHeight,
        READER_PREFERENCE_DEFAULTS.lineHeight,
        1.3,
        2
      ),
      blockSpacing: boundedReaderNumber(
        data.alcReaderBlockSpacing,
        READER_PREFERENCE_DEFAULTS.blockSpacing,
        50,
        150
      ),
      width: boundedReaderNumber(
        data.alcReaderWidth, READER_PREFERENCE_DEFAULTS.width, 50, 150
      )
    };
  }

  function applyReaderPreferences(preferences) {
    var root = document.documentElement;
    var body = document.body;
    var next = Object.assign({}, READER_PREFERENCE_DEFAULTS, preferences || {});
    state.readerPreferences = next;
    root.style.setProperty(
      "--alc-source-font", READER_FONT_STACKS[next.englishFont]
    );
    root.style.setProperty(
      "--alc-target-font", READER_FONT_STACKS[next.chineseFont]
    );
    root.style.setProperty("--alc-font-scale", String(next.scale / 100));
    root.style.setProperty(
      "--alc-reader-line-height", String(next.lineHeight)
    );
    root.style.setProperty(
      "--alc-reader-supplement-line-height",
      (1.55 * next.lineHeight / 1.65).toFixed(3)
    );
    root.style.setProperty(
      "--alc-reader-block-padding",
      (0.4 * next.blockSpacing / 100).toFixed(3) + "rem"
    );
    root.style.setProperty(
      "--alc-reader-source-block-padding",
      (0.3 * next.blockSpacing / 100).toFixed(3) + "rem"
    );
    root.style.setProperty(
      "--alc-reader-supplement-block-padding",
      (0.45 * next.blockSpacing / 100).toFixed(3) + "rem"
    );
    root.style.setProperty(
      "--alc-reader-block-gap",
      Math.max(0, 0.8 * (next.blockSpacing - 100) / 100).toFixed(3) + "rem"
    );
    root.style.setProperty(
      "--alc-reader-width", String(96 * next.width / 100) + "rem"
    );
    body.classList.toggle("alc-stacked-layout", next.layout === "stacked");
    body.dataset.alcReaderLayout = next.layout;
    body.dataset.alcReaderEditActivation = next.editActivation;
    body.dataset.alcReaderEnglishFont = next.englishFont;
    body.dataset.alcReaderChineseFont = next.chineseFont;
    body.dataset.alcReaderScale = String(next.scale);
    body.dataset.alcReaderLineHeight = String(next.lineHeight);
    body.dataset.alcReaderBlockSpacing = String(next.blockSpacing);
    body.dataset.alcReaderWidth = String(next.width);
    syncReaderPreferenceControls();
    scheduleScrollableTableSync();
  }

  function syncReaderPreferenceControls() {
    var preferences = state.readerPreferences;
    var values = {
      "alc-settings-layout": preferences.layout,
      "alc-settings-edit": preferences.editActivation,
      "alc-settings-english-font": preferences.englishFont,
      "alc-settings-chinese-font": preferences.chineseFont,
      "alc-settings-scale": String(preferences.scale),
      "alc-settings-line": String(preferences.lineHeight),
      "alc-settings-block-spacing": String(preferences.blockSpacing),
      "alc-settings-width": String(preferences.width)
    };
    Object.keys(values).forEach(function (identifier) {
      var control = document.getElementById(identifier);
      if (control) {
        control.value = values[identifier];
        syncCustomSelect(control);
      }
    });
    var scale = document.getElementById("alc-settings-scale-value");
    var line = document.getElementById("alc-settings-line-value");
    var blockSpacing = document.getElementById(
      "alc-settings-block-spacing-value"
    );
    var width = document.getElementById("alc-settings-width-value");
    if (scale) scale.textContent = Math.round(preferences.scale) + "%";
    if (line) line.textContent = Number(preferences.lineHeight).toFixed(2);
    if (blockSpacing) {
      blockSpacing.textContent = Math.round(preferences.blockSpacing) + "%";
    }
    if (width) width.textContent = Math.round(preferences.width) + "%";
  }

  function setupReaderSettings() {
    var strings = labels();
    var control = document.querySelector(".alc-settings-control");
    var trigger = document.getElementById("alc-settings");
    var panel = document.getElementById("alc-settings-panel");
    var close = document.getElementById("alc-settings-close");
    labelToolButton(trigger, strings.moreSettings);
    document.getElementById("alc-settings-heading").textContent =
      strings.moreSettings;
    close.setAttribute("aria-label", strings.closeMoreSettings);
    document.getElementById("alc-settings-layout-label").textContent =
      strings.translationLayout;
    document.getElementById("alc-settings-edit-label").textContent =
      strings.enterEditMode;
    document.getElementById("alc-settings-english-font-label").textContent =
      strings.englishFont;
    document.getElementById("alc-settings-chinese-font-label").textContent =
      strings.chineseFont;
    document.getElementById("alc-settings-scale-label").textContent =
      strings.displayScale;
    document.getElementById("alc-settings-line-label").textContent =
      strings.readerLineHeight;
    document.getElementById("alc-settings-block-spacing-label").textContent =
      strings.readerBlockSpacing;
    document.getElementById("alc-settings-width-label").textContent =
      strings.contentWidth;
    document.getElementById("alc-settings-note").textContent = strings.settingsNote;
    document.getElementById("alc-settings-reset").textContent =
      strings.restoreRecommended;
    var layout = document.getElementById("alc-settings-layout");
    layout.options[0].textContent = strings.parallelLayout;
    layout.options[1].textContent = strings.stackedLayout;
    var activation = document.getElementById("alc-settings-edit");
    activation.options[0].textContent = strings.doubleClick;
    activation.options[1].textContent = strings.singleClick;
    [
      document.getElementById("alc-settings-english-font"),
      document.getElementById("alc-settings-chinese-font")
    ].forEach(function (select) {
      if (select && select.options.length) {
        select.options[0].textContent = strings.systemDefault;
      }
    });
    [layout, activation,
      document.getElementById("alc-settings-english-font"),
      document.getElementById("alc-settings-chinese-font")
    ].forEach(function (select) {
      installCustomSelect(select);
      var wrapper = customSelectRegistry.get(select);
      if (wrapper) wrapper.dataset.compact = "true";
    });

    state.readerPreferences = readerPreferenceSnapshot();
    applyReaderPreferences(state.readerPreferences);
    state.readerSettingsReady = true;

    trigger.addEventListener("click", function () {
      panel.hidden = !panel.hidden;
      trigger.setAttribute("aria-expanded", String(!panel.hidden));
      if (!panel.hidden) {
        positionToolPanel(panel);
        close.focus();
      }
    });
    window.addEventListener("resize", function () { positionToolPanel(panel); });
    close.addEventListener("click", function () {
      panel.hidden = true;
      trigger.setAttribute("aria-expanded", "false");
      trigger.focus();
    });
    [layout, activation,
      document.getElementById("alc-settings-english-font"),
      document.getElementById("alc-settings-chinese-font")
    ].forEach(function (select) {
      select.addEventListener("change", function () {
        applyReaderPreferences({
          layout: layout.value,
          editActivation: activation.value,
          englishFont: document.getElementById("alc-settings-english-font").value,
          chineseFont: document.getElementById("alc-settings-chinese-font").value,
          scale: state.readerPreferences.scale,
          lineHeight: state.readerPreferences.lineHeight,
          blockSpacing: state.readerPreferences.blockSpacing,
          width: state.readerPreferences.width
        });
      });
    });
    ["scale", "line", "block-spacing", "width"].forEach(function (name) {
      document.getElementById("alc-settings-" + name).addEventListener(
        "input", function (event) {
          var changes = {};
          if (name === "scale") changes.scale = Number(event.target.value);
          if (name === "line") changes.lineHeight = Number(event.target.value);
          if (name === "block-spacing") {
            changes.blockSpacing = Number(event.target.value);
          }
          if (name === "width") changes.width = Number(event.target.value);
          applyReaderPreferences(Object.assign({}, state.readerPreferences, changes));
        }
      );
    });
    document.getElementById("alc-settings-reset").addEventListener(
      "click", function () {
        applyReaderPreferences(Object.assign({}, READER_PREFERENCE_DEFAULTS));
      }
    );
    document.addEventListener("click", function (event) {
      if (!panel.hidden && !control.contains(event.target)) {
        panel.hidden = true;
        trigger.setAttribute("aria-expanded", "false");
      }
    });
    document.addEventListener("keydown", function (event) {
      if (event.key === "Escape" && !panel.hidden) {
        event.preventDefault();
        panel.hidden = true;
        trigger.setAttribute("aria-expanded", "false");
        trigger.focus();
      }
    });
  }

  function selectListbox(wrapper) {
    return wrapper && (
      wrapper._alcListbox || wrapper.querySelector(".alc-select-listbox")
    );
  }

  function closeCustomSelect(wrapper, restoreFocus) {
    if (!wrapper) return;
    var trigger = wrapper.querySelector(".alc-select-trigger");
    var listbox = selectListbox(wrapper);
    if (!trigger || !listbox) return;
    listbox.hidden = true;
    trigger.setAttribute("aria-expanded", "false");
    if (restoreFocus) trigger.focus();
  }

  function closeOtherCustomSelects(current) {
    document.querySelectorAll(".alc-custom-select").forEach(function (wrapper) {
      if (wrapper !== current) closeCustomSelect(wrapper, false);
    });
  }

  function customSelectOptions(wrapper) {
    return Array.prototype.slice.call(
      selectListbox(wrapper).querySelectorAll('[role="option"]')
    );
  }

  function positionCustomSelect(wrapper) {
    var trigger = wrapper.querySelector(".alc-select-trigger");
    var listbox = selectListbox(wrapper);
    if (!trigger || !listbox) return;
    var rectangle = trigger.getBoundingClientRect();
    var gutter = 8;
    var below = window.innerHeight - rectangle.bottom - gutter;
    var above = rectangle.top - gutter;
    var opensBelow = below >= 176 || below >= above;
    var available = Math.max(112, (opensBelow ? below : above) - gutter);
    var compact = wrapper.dataset.compact === "true";
    var width = Math.min(
      compact ? rectangle.width : Math.max(rectangle.width, 176),
      window.innerWidth - gutter * 2
    );
    var left = Math.min(
      Math.max(gutter, rectangle.left), window.innerWidth - width - gutter
    );
    listbox.style.width = width + "px";
    listbox.style.left = left + "px";
    listbox.style.right = "auto";
    listbox.style.maxHeight = Math.min(compact ? 240 : 320, available) + "px";
    if (opensBelow) {
      listbox.style.top = rectangle.bottom + 5 + "px";
      listbox.style.bottom = "auto";
    } else {
      listbox.style.top = "auto";
      listbox.style.bottom = window.innerHeight - rectangle.top + 5 + "px";
    }
  }

  function openCustomSelect(wrapper, focusSelected) {
    var trigger = wrapper.querySelector(".alc-select-trigger");
    var listbox = selectListbox(wrapper);
    if (!trigger || !listbox || trigger.disabled) return;
    closeOtherCustomSelects(wrapper);
    var host = wrapper.closest("dialog[open]") || document.body;
    if (listbox.parentElement !== host) host.appendChild(listbox);
    listbox.hidden = false;
    positionCustomSelect(wrapper);
    trigger.setAttribute("aria-expanded", "true");
    if (focusSelected) {
      var options = customSelectOptions(wrapper);
      var selected = options.find(function (option) {
        return option.getAttribute("aria-selected") === "true";
      }) || options[0];
      if (selected) selected.focus();
    }
  }

  function syncCustomSelect(select) {
    var wrapper = customSelectRegistry.get(select);
    if (!wrapper) return;
    var trigger = wrapper.querySelector(".alc-select-trigger");
    var value = wrapper.querySelector(".alc-select-value");
    var listbox = selectListbox(wrapper);
    var selected = select.options[select.selectedIndex] || select.options[0];
    trigger.disabled = select.disabled;
    value.textContent = selected ? selected.textContent : "";
    listbox.replaceChildren();
    Array.prototype.forEach.call(select.options, function (nativeOption) {
      var option = element("button", "alc-select-option", nativeOption.textContent);
      option.type = "button";
      option.setAttribute("role", "option");
      option.setAttribute(
        "aria-selected", String(nativeOption.value === select.value)
      );
      option.dataset.value = nativeOption.value;
      option.addEventListener("click", function () {
        select.value = option.dataset.value;
        select.dispatchEvent(new window.Event("change", {bubbles: true}));
        syncCustomSelect(select);
        closeCustomSelect(wrapper, true);
      });
      option.addEventListener("keydown", function (event) {
        var options = customSelectOptions(wrapper);
        var index = options.indexOf(option);
        var target = -1;
        if (event.key === "ArrowDown") {
          target = Math.min(options.length - 1, index + 1);
        } else if (event.key === "ArrowUp") {
          target = Math.max(0, index - 1);
        } else if (event.key === "Home") target = 0;
        else if (event.key === "End") target = options.length - 1;
        else if (event.key === "Escape") {
          event.preventDefault();
          closeCustomSelect(wrapper, true);
          return;
        }
        if (target >= 0) {
          event.preventDefault();
          options[target].focus();
        }
      });
      listbox.appendChild(option);
    });
  }

  function selectChevronMarkup() {
    return '<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">' +
      '<path d="m7 9.5 5 5 5-5"></path></svg>';
  }

  function hideNativeSelectForCustomControl(select) {
    select.classList.add("alc-native-select");
    select.tabIndex = -1;
    select.setAttribute("aria-hidden", "true");
  }

  function installCustomSelect(select) {
    if (!select || customSelectRegistry.has(select)) return;
    if (!select.id) {
      customSelectSerial += 1;
      select.id = "alc-select-" + customSelectSerial;
    }
    var listboxId = select.id + "-listbox";
    var wrapper = element("div", "alc-custom-select");
    wrapper.innerHTML =
      '<button type="button" class="alc-select-trigger" aria-haspopup="listbox" ' +
        'aria-expanded="false" aria-controls="' + listboxId + '">' +
        '<span class="alc-select-value"></span>' + selectChevronMarkup() +
      '</button>' +
      '<div id="' + listboxId + '" class="alc-select-listbox" ' +
        'role="listbox" hidden></div>';
    hideNativeSelectForCustomControl(select);
    select.insertAdjacentElement("afterend", wrapper);
    var listbox = wrapper.querySelector(".alc-select-listbox");
    wrapper._alcListbox = listbox;
    customSelectRegistry.set(select, wrapper);
    var trigger = wrapper.querySelector(".alc-select-trigger");
    var value = wrapper.querySelector(".alc-select-value");
    value.id = select.id + "-value";
    var field = select.closest(
      ".alc-settings-field, .alc-speech-field, .alc-dialog-fields label"
    );
    var label = field && field.querySelector(":scope > span");
    if (label) {
      if (!label.id) label.id = select.id + "-label";
      trigger.setAttribute("aria-labelledby", label.id + " " + value.id);
      listbox.setAttribute("aria-labelledby", label.id);
    } else {
      trigger.setAttribute("aria-labelledby", value.id);
    }
    wrapper.addEventListener("click", function (event) {
      event.stopPropagation();
    });
    listbox.addEventListener("click", function (event) {
      event.stopPropagation();
    });
    trigger.addEventListener("click", function () {
      if (listbox.hidden) openCustomSelect(wrapper, false);
      else closeCustomSelect(wrapper, false);
    });
    trigger.addEventListener("keydown", function (event) {
      if (["ArrowDown", "ArrowUp", "Home", "End"].indexOf(event.key) < 0) return;
      event.preventDefault();
      openCustomSelect(wrapper, true);
      var options = customSelectOptions(wrapper);
      if (event.key === "End" && options.length) options[options.length - 1].focus();
      if (event.key === "Home" && options.length) options[0].focus();
    });
    syncCustomSelect(select);
  }

  function setupCustomSelectEvents() {
    document.addEventListener("pointerdown", function (event) {
      if (event.target.closest && event.target.closest(
        ".alc-custom-select, .alc-select-listbox"
      )) return;
      closeOtherCustomSelects(null);
    }, true);
    document.addEventListener("keydown", function (event) {
      if (event.key !== "Escape") return;
      var open = Array.prototype.find.call(
        document.querySelectorAll(".alc-custom-select"), function (wrapper) {
          return !selectListbox(wrapper).hidden;
        }
      );
      if (open) {
        event.preventDefault();
        event.stopPropagation();
        closeCustomSelect(open, true);
      }
    }, true);
    document.addEventListener("scroll", function (event) {
      if (event.target.closest && event.target.closest(".alc-select-listbox")) return;
      closeOtherCustomSelects(null);
    }, true);
    window.addEventListener("resize", function () {
      closeOtherCustomSelects(null);
    });
  }

  function setupMarkdown() {
    if (typeof window.markdownit !== "function") {
      throw new Error("embedded markdown-it is unavailable");
    }
    var md = window.markdownit("commonmark", {
      html: false,
      linkify: false,
      typographer: false,
      breaks: false
    });
    md.enable("table");

    md.inline.ruler.before("escape", "alc_math_inline", function (parserState, silent) {
      var source = parserState.src;
      var position = parserState.pos;
      var open;
      var close;
      if (source.slice(position, position + 2) === "\\(") {
        open = "\\(";
        close = "\\)";
      } else if (
        source.charAt(position) === "$" &&
        source.slice(position, position + 2) !== "$$" &&
        (position === 0 || source.charAt(position - 1) !== "\\")
      ) {
        open = "$";
        close = "$";
      } else {
        return false;
      }
      var start = position + open.length;
      var end = inlineMathEnd(source, start, close);
      if (end < 0 || end === start || source.slice(start, end).indexOf("\n") >= 0) {
        return false;
      }
      if (!silent) {
        var token = parserState.push("alc_math_inline", "span", 0);
        token.content = source.slice(start, end).trim();
      }
      parserState.pos = end + close.length;
      return true;
    });

    md.inline.ruler.before("text", "alc_citation", function (parserState, silent) {
      var match = /^\[@([A-Za-z0-9][A-Za-z0-9._:-]*)\]/.exec(
        parserState.src.slice(parserState.pos)
      );
      if (!match) return false;
      if (!silent) {
        var token = parserState.push("alc_citation", "a", 0);
        token.content = match[1];
      }
      parserState.pos += match[0].length;
      return true;
    });

    md.block.ruler.before("fence", "alc_math_block", function (
      parserState, startLine, endLine, silent
    ) {
      var begin = parserState.bMarks[startLine] + parserState.tShift[startLine];
      var maximum = parserState.eMarks[startLine];
      var opening = parserState.src.slice(begin, maximum).trim();
      var legacySingleLine = (
        opening.length > 4 && opening.slice(0, 2) === "$$" &&
        opening.slice(-2) === "$$" &&
        opening.slice(2, -2).indexOf("$$") < 0
      );
      if (legacySingleLine) {
        if (silent) return true;
        var legacyToken = parserState.push("alc_math_block", "div", 0);
        legacyToken.block = true;
        legacyToken.map = [startLine, startLine + 1];
        legacyToken.content = opening.slice(2, -2).trim();
        parserState.line = startLine + 1;
        return true;
      }
      var closing = opening === "$$" ? "$$" : opening === "\\[" ? "\\]" : null;
      if (!closing) return false;
      var line = startLine + 1;
      while (line < endLine) {
        var lineStart = parserState.bMarks[line] + parserState.tShift[line];
        var lineEnd = parserState.eMarks[line];
        if (parserState.src.slice(lineStart, lineEnd).trim() === closing) break;
        line += 1;
      }
      if (line >= endLine) return false;
      if (silent) return true;
      var token = parserState.push("alc_math_block", "div", 0);
      token.block = true;
      token.map = [startLine, line + 1];
      token.content = parserState.getLines(
        startLine + 1, line, parserState.blkIndent, false
      ).trim();
      parserState.line = line + 1;
      return true;
    });

    md.renderer.rules.alc_math_inline = function (tokens, index) {
      return '<span class="math math-inline" data-tex="' +
        md.utils.escapeHtml(tokens[index].content) + '">' +
        md.utils.escapeHtml(tokens[index].content) + "</span>";
    };
    md.renderer.rules.alc_math_block = function (tokens, index) {
      return '<div class="math math-display" data-tex="' +
        md.utils.escapeHtml(tokens[index].content) + '">' +
        md.utils.escapeHtml(tokens[index].content) + "</div>";
    };
    md.renderer.rules.alc_citation = function (tokens, index, _options, env) {
      var citationId = tokens[index].content;
      var number = (env.citationNumbers || {})[citationId];
      var targetId = (env.citationTargets || {})[citationId] || citationId;
      var visible = number === undefined ? "?" : String(number);
      return '<a class="alc-citation" href="#reference-' +
        md.utils.escapeHtml(targetId) + '">[' +
        md.utils.escapeHtml(visible) + "]</a>";
    };
    md.renderer.rules.image = function (tokens, index) {
      var token = tokens[index];
      var alternative = md.utils.escapeHtml(token.content || "");
      var source = token.attrGet("src") || "";
      var resource = resourceForLogicalName(source);
      if (resource && typeof resource.data_uri === "string") {
        return '<img class="alc-markdown-image" src="' +
          md.utils.escapeHtml(resource.data_uri) + '" alt="' + alternative +
          '" loading="lazy" decoding="async">';
      }
      var text = md.utils.escapeHtml(labels().imageOmitted);
      return '<span class="alc-markdown-image" role="note">[' + text +
        (alternative ? ": " + alternative : "") + "]</span>";
    };
    var defaultLinkOpen = md.renderer.rules.link_open || function (
      tokens, index, options, _env, renderer
    ) {
      return renderer.renderToken(tokens, index, options);
    };
    md.renderer.rules.link_open = function (tokens, index, options, env, renderer) {
      tokens[index].attrSet("rel", "noopener noreferrer");
      return defaultLinkOpen(tokens, index, options, env, renderer);
    };
    state.md = md;
    if (typeof window.addEventListener === "function") {
      window.addEventListener("resize", scheduleScrollableTableSync);
    }
  }

  function inlineMathEnd(source, start, close) {
    var braceDepth = 0;
    for (var index = start; index < source.length; index += 1) {
      var escaped = false;
      var slashCount = 0;
      for (var cursor = index - 1; cursor >= 0 && source.charAt(cursor) === "\\"; cursor -= 1) {
        slashCount += 1;
      }
      escaped = slashCount % 2 === 1;
      if (!escaped && close === "$" && source.charAt(index) === "{") {
        braceDepth += 1;
      } else if (
        !escaped && close === "$" && source.charAt(index) === "}" && braceDepth
      ) {
        braceDepth -= 1;
      } else if (
        !escaped && braceDepth === 0 && source.slice(index, index + close.length) === close
      ) {
        return index;
      }
    }
    return -1;
  }

  function bibliographyIdentity(entry) {
    var arxiv = (entry.arxiv_ids || []).map(function (value) {
      return String(value).trim().toLowerCase().replace(/^arxiv:/, "");
    }).filter(Boolean).sort();
    if (arxiv.length) return "arxiv:" + arxiv[0];
    var dois = (entry.dois || []).map(function (value) {
      return String(value).trim().toLowerCase().replace(/^https?:\/\/doi[.]org\//, "");
    }).filter(Boolean).sort();
    if (dois.length) return "doi:" + dois[0];
    var source = String(entry.source || entry.url || "")
      .trim().toLowerCase().replace(/\/$/, "");
    var id = entry.evidence_id || entry.citation_id || entry.id || "";
    return source ? "source:" + source : "id:" + id;
  }

  function bibliographyIndex() {
    if (state.bibliographyIndexCache) return state.bibliographyIndexCache;
    var groups = [];
    var byIdentity = new Map();
    var numbers = {};
    var targets = {};
    (state.payload.publication.bibliography || []).forEach(function (entry) {
      var id = entry.evidence_id || entry.citation_id || entry.id || "";
      var identity = bibliographyIdentity(entry);
      var group = byIdentity.get(identity);
      if (!group) {
        group = {
          entry: entry,
          targetId: id,
          number: groups.length + 1
        };
        byIdentity.set(identity, group);
        groups.push(group);
      }
      if (id) {
        numbers[id] = group.number;
        targets[id] = group.targetId || id;
        if (!group.targetId) group.targetId = id;
      }
    });
    state.bibliographyIndexCache = {
      groups: groups,
      numbers: numbers,
      targets: targets
    };
    return state.bibliographyIndexCache;
  }

  function citationNumbers() {
    return bibliographyIndex().numbers;
  }

  function citationTargets() {
    return bibliographyIndex().targets;
  }

  function renderMarkdown(markdown, fragment, options) {
    var wrapper = element("div", "alc-markdown");
    var source = fragment && fragment.role !== "source" ?
      projectGlossaryMarkdown(markdown, fragment) : normalizeMarkdown(markdown);
    wrapper.innerHTML = state.md.render(source, {
      citationNumbers: citationNumbers(),
      citationTargets: citationTargets()
    });
    removeVisibleHtmlTags(wrapper);
    decorateLegacyBibliographyLinks(wrapper);
    decorateLegacyStructuralLinks(wrapper);
    decorateScrollableTables(wrapper);
    if (!options || options.decorateGlossary !== false) {
      decorateGlossary(wrapper, "target");
    }
    typeset(wrapper);
    return wrapper;
  }

  function renderGlossaryDefinition(markdown, options) {
    var recovered = glossaryDefinitionHasForbiddenControl(markdown);
    var rendered = renderMarkdown(
      recovered ? recoverLegacyGlossaryDefinition(markdown) : markdown,
      null,
      options
    );
    rendered.classList.add("alc-glossary-definition-markdown");
    if (recovered) {
      rendered.classList.add("alc-glossary-definition-recovered");
      rendered.setAttribute("role", "status");
      rendered.setAttribute("title", labels().glossaryDefinitionRecovered);
    }
    return rendered;
  }

  function glossaryTranslatedTermMarkup(value) {
    var text = String(value || "");
    var hasInlineMath = /\$[^$\r\n]+\$/.test(text) ||
      /\\\([^\r\n]+\\\)/.test(text);
    if (!hasInlineMath) return null;
    return state.md.renderInline(text, {
      citationNumbers: citationNumbers(),
      citationTargets: citationTargets()
    });
  }

  function appendGlossaryTranslatedTerm(root, value) {
    var text = String(value || "");
    var markup = glossaryTranslatedTermMarkup(text);
    if (markup === null) {
      root.textContent = text;
      return false;
    }
    var recovered = element(
      "span", "alc-glossary-translated-term-recovered"
    );
    recovered.innerHTML = markup;
    removeVisibleHtmlTags(recovered);
    root.appendChild(recovered);
    return true;
  }

  function glossaryDefinitionHasForbiddenControl(value) {
    return /[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f-\u009f]/.test(
      String(value || "")
    );
  }

  function recoverLegacyGlossaryDefinition(value) {
    return String(value || "")
      .replace(
        /(?:\u001b\[|\u009b)[0-9:;]{0,32}m/g,
        ""
      )
      .replace(
        /([\u0001-\u0008\u000b\u000c\u000e-\u001f])([0-9a-f]{2})(?![0-9a-f])/gi,
        function (_match, highByte, suffix) {
          return String.fromCodePoint(
            highByte.charCodeAt(0) * 256 + parseInt(suffix, 16)
          );
        }
      )
      .replace(/\u001d/g, "")
      .replace(/[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f-\u009f]/g, "?");
  }

  function glossaryDefinitionPlainText(value) {
    return markdownPlainText(
      glossaryDefinitionHasForbiddenControl(value) ?
        recoverLegacyGlossaryDefinition(value) : value || ""
    );
  }

  function markdownPlainText(markdown) {
    var tokens = state.md.parse(normalizeMarkdown(markdown), {});
    var parts = [];
    tokens.forEach(function (token) {
      if (token.type === "inline") {
        var inline = markdownInlinePlainText(token.children || []);
        if (inline) parts.push(inline);
      } else if (
        token.type === "alc_math_block" || token.type === "code_block" ||
        token.type === "fence"
      ) {
        if (token.content) parts.push(token.content);
      }
    });
    return normalizeSpeechText(parts.join("\n"));
  }

  function markdownInlinePlainText(tokens) {
    var values = [];
    tokens.forEach(function (token) {
      if (Array.isArray(token.children) && token.children.length) {
        values.push(markdownInlinePlainText(token.children));
      } else if (
        token.type === "text" || token.type === "code_inline" ||
        token.type === "alc_math_inline" || token.type === "html_inline"
      ) {
        values.push(token.content || "");
      } else if (token.type === "alc_citation") {
        var number = citationNumbers()[token.content];
        values.push("[" + (number === undefined ? token.content : number) + "]");
      } else if (token.type === "image") {
        values.push(token.content || "");
      } else if (token.type === "softbreak" || token.type === "hardbreak") {
        values.push("\n");
      }
    });
    return values.join("");
  }

  function normalizeMarkdown(value) {
    var normalized = String(value || "").replace(/\r\n?/g, "\n").normalize("NFC");
    if (normalized.indexOf("\u0000") >= 0) {
      throw new Error("Markdown body cannot contain NUL");
    }
    return normalized;
  }

  function canonicalizeLegacyDisplayMath(markdown) {
    var normalized = normalizeMarkdown(markdown);
    var codeLines = markdownCodeLineIndexes(normalized);
    var output = [];
    normalized.split("\n").forEach(function (line, lineNumber) {
      if (codeLines.has(lineNumber)) {
        output.push(line);
        return;
      }
      var match = /^([ \t]*)[$][$](.+)[$][$][ \t]*$/.exec(line);
      if (match && match[2].trim() && match[2].indexOf("$$") < 0) {
        output.push(match[1] + "$$");
        output.push(match[1] + match[2].trim());
        output.push(match[1] + "$$");
        return;
      }
      output.push(line);
    });
    return output.join("\n");
  }

  function removeVisibleHtmlTags(root) {
    var walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
    var nodes = [];
    var current;
    while ((current = walker.nextNode())) nodes.push(current);
    nodes.forEach(function (node) {
      if (node.parentElement && node.parentElement.closest("code, pre, .math")) return;
      node.nodeValue = node.nodeValue.replace(/<\/?[A-Za-z][^>]*>/g, "");
    });
  }

  function glossarySourceTerm(entry) {
    return String(entry && (entry.term || entry.source_term) || "");
  }

  function glossaryTranslatedKey(entry) {
    if (entry && Object.prototype.hasOwnProperty.call(entry, "translated_term")) {
      return "translated_term";
    }
    if (entry && Object.prototype.hasOwnProperty.call(entry, "translation")) {
      return "translation";
    }
    return null;
  }

  function glossaryEntryId(entry) {
    return entry && typeof entry.entry_id === "string" ? entry.entry_id : "";
  }

  function glossaryEntryHasEditableShape(entry) {
    var translatedKey = glossaryTranslatedKey(entry);
    return Boolean(
      entry && portableIdentifier(glossaryEntryId(entry)) &&
      glossarySourceTerm(entry).trim() && translatedKey &&
      typeof entry[translatedKey] === "string" &&
      typeof entry.definition === "string"
    );
  }

  function glossaryEntryIsEditable(entry) {
    if (!glossaryEntryHasEditableShape(entry)) return false;
    if (
      glossaryDefinitionHasForbiddenControl(entry.definition) ||
      glossaryDefinitionHasForbiddenControl(
        entry[glossaryTranslatedKey(entry)]
      )
    ) return false;
    try {
      validateIntegerJson(entry, "glossary entry");
      return true;
    } catch (_error) {
      return false;
    }
  }

  function glossaryEntryEditableInState(entry) {
    return glossaryEntryIsEditable(entry) &&
      !state.glossaryDuplicateIds.has(glossaryEntryId(entry));
  }

  function glossaryBaseMaterial(entry) {
    return {
      schema_version: GLOSSARY_REVISION_SCHEMA,
      entry_id: glossaryEntryId(entry),
      revision: 1,
      entry: JSON.parse(JSON.stringify(entry))
    };
  }

  function glossaryRevisionMaterial(revision) {
    return {
      schema_version: revision.schema_version,
      entry_id: revision.entry_id,
      revision: revision.revision,
      parent_semantic_digest: revision.parent_semantic_digest,
      entry: JSON.parse(JSON.stringify(revision.entry)),
      provenance: JSON.parse(JSON.stringify(revision.provenance))
    };
  }

  function encodeGlossaryRevision(metadata) {
    var storage = glossaryRevisionMaterial(metadata);
    var definition = normalizeMarkdown(storage.entry.definition);
    delete storage.entry.definition;
    return GLOSSARY_FRONT_BEGIN + "\n" + stableStringify(storage) + "\n" +
      GLOSSARY_FRONT_END + "\n" + definition;
  }

  async function canonicalDigest(value) {
    if (!crypto.subtle) throw new Error("Web Crypto is required for glossary revisions");
    var bytes = new TextEncoder().encode(stableStringify(value));
    var digest = await crypto.subtle.digest("SHA-256", bytes);
    return Array.from(new Uint8Array(digest)).map(function (item) {
      return item.toString(16).padStart(2, "0");
    }).join("");
  }

  function glossaryRevisionFileName(revision, digest) {
    return "revision-" + String(revision).padStart(6, "0") + "-" + digest + ".md";
  }

  function validateGlossaryRevisionMetadata(metadata) {
    requireExactObject(metadata, [
      "schema_version", "entry_id", "revision", "parent_semantic_digest",
      "entry", "provenance"
    ], "glossary revision");
    if (
      metadata.schema_version !== GLOSSARY_REVISION_SCHEMA ||
      !portableIdentifier(metadata.entry_id) ||
      !Number.isSafeInteger(metadata.revision) || metadata.revision < 2 ||
      !digestValue(metadata.parent_semantic_digest) ||
      !plainObject(metadata.entry) || !plainObject(metadata.provenance) ||
      glossaryEntryId(metadata.entry) !== metadata.entry_id
    ) {
      throw new Error("glossary revision metadata is invalid");
    }
    validateGlossaryPropagation(metadata.provenance.propagation);
    if (metadata.provenance.propagation &&
      (metadata.provenance.propagation.glossary_revisions || []).some(
        function (reference) { return reference.entry_id === metadata.entry_id; }
      )) {
      throw new Error("glossary propagation cannot rewrite its initiating entry");
    }
    validateJsonCompatible(metadata, "glossary revision");
  }

  function glossaryBatchFragmentPath(batchId, fragmentId, revision, digest) {
    return [
      "glossary-batches", batchId, "fragments",
      revisionFilename(revision, digest)
    ].join("/");
  }

  function glossaryBatchGlossaryPath(batchId, revision, digest) {
    return [
      "glossary-batches", batchId, "glossary",
      glossaryRevisionFileName(revision, digest)
    ].join("/");
  }

  function validateGlossaryPropagation(propagation) {
    if (propagation === undefined) return;
    var fields = plainObject(propagation) ? Object.keys(propagation).sort() : [];
    var legacyFields = ["batch_id", "fragments", "schema_version"].sort();
    var extendedFields = [
      "batch_id", "fragments", "glossary_revisions", "schema_version"
    ].sort();
    if (stableStringify(fields) !== stableStringify(legacyFields) &&
      stableStringify(fields) !== stableStringify(extendedFields)) {
      throw new Error("glossary propagation has invalid fields");
    }
    var glossaryRevisions = propagation.glossary_revisions || [];
    if (propagation.schema_version !== GLOSSARY_PROPAGATION_SCHEMA ||
      !portableIdentifier(propagation.batch_id) ||
      !Array.isArray(propagation.fragments) ||
      !Array.isArray(glossaryRevisions) ||
      (!propagation.fragments.length && !glossaryRevisions.length)) {
      throw new Error("glossary propagation is invalid");
    }
    var fragmentIds = new Set();
    var paths = new Set();
    propagation.fragments.forEach(function (reference) {
      requireExactObject(reference, [
        "path", "fragment_id", "revision", "parent_semantic_digest",
        "semantic_digest"
      ], "glossary propagation fragment");
      if (!portableIdentifier(reference.fragment_id) ||
        !positiveInteger(reference.revision) || reference.revision < 2 ||
        !digestValue(reference.parent_semantic_digest) ||
        !digestValue(reference.semantic_digest) ||
        reference.path !== glossaryBatchFragmentPath(
          propagation.batch_id, reference.fragment_id, reference.revision,
          reference.semantic_digest
        ) || fragmentIds.has(reference.fragment_id) || paths.has(reference.path)) {
        throw new Error("glossary propagation fragment is invalid");
      }
      fragmentIds.add(reference.fragment_id);
      paths.add(reference.path);
    });
    var entryIds = new Set();
    glossaryRevisions.forEach(function (reference) {
      requireExactObject(reference, [
        "path", "entry_id", "revision", "parent_semantic_digest",
        "semantic_digest"
      ], "glossary propagation dependent revision");
      if (!portableIdentifier(reference.entry_id) ||
        !positiveInteger(reference.revision) || reference.revision < 2 ||
        !digestValue(reference.parent_semantic_digest) ||
        !digestValue(reference.semantic_digest) ||
        reference.path !== glossaryBatchGlossaryPath(
          propagation.batch_id, reference.revision,
          reference.semantic_digest
        ) || entryIds.has(reference.entry_id) || paths.has(reference.path)) {
        throw new Error("glossary propagation dependent revision is invalid");
      }
      entryIds.add(reference.entry_id);
      paths.add(reference.path);
    });
  }

  function validGlossaryRevisionChange(base, candidate) {
    if (!glossaryEntryHasEditableShape(base) || !plainObject(candidate)) return false;
    if (!validGlossarySurfaceAnchors(base) || !validGlossarySurfaceAnchors(candidate)) return false;
    if (stableStringify(Object.keys(base).sort()) !==
      stableStringify(Object.keys(candidate).sort())) return false;
    var translatedKey = glossaryTranslatedKey(base);
    return Object.keys(base).every(function (key) {
      if (key === translatedKey || key === "definition") {
        return typeof candidate[key] === "string";
      }
      return jsonValuesEqual(candidate[key], base[key]);
    });
  }

  function validGlossarySurfaceAnchors(entry) {
    if (!Array.isArray(entry.surface_anchors)) {
      return entry.surface_anchors === undefined || entry.surface_anchors === null;
    }
    var ranges = new Map();
    return entry.surface_anchors.every(function (anchor) {
      if (!plainObject(anchor) || stableStringify(Object.keys(anchor).sort()) !==
        stableStringify([
          "block_id", "fragment_id", "fragment_semantic_digest",
          "markdown_start", "markdown_end", "surface"
        ].sort())) return false;
      if (!portableIdentifier(anchor.block_id) || !portableIdentifier(anchor.fragment_id) ||
        !digestValue(anchor.fragment_semantic_digest) ||
        !Number.isSafeInteger(anchor.markdown_start) || anchor.markdown_start < 0 ||
        !Number.isSafeInteger(anchor.markdown_end) || anchor.markdown_end <= anchor.markdown_start ||
        typeof anchor.surface !== "string" || !anchor.surface) return false;
      var key = anchor.block_id + "\u0000" + anchor.fragment_id +
        "\u0000" + anchor.fragment_semantic_digest;
      var values = ranges.get(key) || [];
      if (values.some(function (range) {
        return anchor.markdown_start < range[1] && range[0] < anchor.markdown_end;
      })) return false;
      values.push([anchor.markdown_start, anchor.markdown_end]);
      ranges.set(key, values);
      return true;
    });
  }

  function glossaryEntryTargetsFragment(entry, fragment) {
    return Boolean(
      glossaryEntryEditableInState(entry) && fragment && fragment.deleted !== true &&
      GLOSSARY_PROPAGATION_ROLES.indexOf(fragment.role) >= 0
    );
  }

  function glossaryTranslatedSurface(entry) {
    var key = glossaryTranslatedKey(entry);
    return key ? String(entry[key] || "").normalize("NFC").trim() : "";
  }

  function glossaryHistoricalSurfaces(entryId, currentSurface) {
    var values = [];
    var seen = new Set();
    function append(entry) {
      var surface = glossaryTranslatedSurface(entry);
      if (surface && !seen.has(surface)) {
        seen.add(surface);
        values.push(surface);
      }
    }
    if (currentSurface) {
      seen.add(currentSurface);
      values.push(currentSurface);
    }
    append(glossaryBaseEntry(entryId));
    (state.glossaryRevisions.get(entryId) || []).forEach(function (revision) {
      append(revision.entry);
    });
    return values;
  }

  function glossaryProtectedMarkdownRanges(markdown) {
    var value = normalizeMarkdown(markdown);
    var lines = value.split("\n");
    var codeLines = markdownCodeLineIndexes(value);
    var ranges = [];
    var lineOffset = 0;
    function protect(start, end) {
      if (Number.isSafeInteger(start) && Number.isSafeInteger(end) && end > start) {
        ranges.push([start, end]);
      }
    }
    lines.forEach(function (line, lineNumber) {
      var lineEnd = lineOffset + line.length;
      if (codeLines.has(lineNumber)) {
        protect(lineOffset, lineEnd);
        lineOffset = lineEnd + 1;
        return;
      }
      if (markdownReferenceDefinition(line)) protect(lineOffset, lineEnd);
      var position = 0;
      while (position < line.length) {
        if (line.charAt(position) === "`") {
          var run = 1;
          while (line.charAt(position + run) === "`") run += 1;
          var codeEnd = markdownCodeSpanEnd(line, position + run, run);
          protect(
            lineOffset + position,
            lineOffset + (codeEnd < 0 ? line.length : codeEnd + run)
          );
          position = codeEnd < 0 ? line.length : codeEnd + run;
          continue;
        }
        var bracket = line.charAt(position) === "[" ? position :
          line.slice(position, position + 2) === "![" ? position + 1 : -1;
        if (bracket >= 0 && !markdownCharacterEscaped(line, bracket)) {
          var labelEnd = markdownLabelEnd(line, bracket);
          if (labelEnd >= 0) {
            var label = line.slice(bracket + 1, labelEnd);
            if (/(?:^|[;\s])-?@[A-Za-z0-9]/.test(label)) {
              protect(lineOffset + bracket, lineOffset + labelEnd + 1);
            }
            if (line.charAt(labelEnd + 1) === "(") {
              var destination = markdownDestinationRange(line, labelEnd + 2);
              if (destination) {
                protect(
                  lineOffset + destination.start,
                  lineOffset + destination.end
                );
              }
            }
          }
        }
        if (line.charAt(position) === "<" && !markdownCharacterEscaped(line, position)) {
          var angleEnd = line.indexOf(">", position + 1);
          if (angleEnd >= 0) protect(lineOffset + position, lineOffset + angleEnd + 1);
        }
        position += 1;
      }
      var urlPattern = /(?:https?:\/\/|mailto:)[^\s<>)]+/g;
      var url;
      while ((url = urlPattern.exec(line))) {
        protect(lineOffset + url.index, lineOffset + url.index + url[0].length);
      }
      lineOffset = lineEnd + 1;
    });
    var mathStart = null;
    var mathRun = 0;
    for (var index = 0; index < value.length; index += 1) {
      if (value.charAt(index) !== "$" || markdownCharacterEscaped(value, index)) continue;
      var delimiter = value.charAt(index + 1) === "$" ? 2 : 1;
      if (mathStart === null) {
        mathStart = index;
        mathRun = delimiter;
        index += delimiter - 1;
      } else if (delimiter === mathRun) {
        protect(mathStart, index + delimiter);
        mathStart = null;
        mathRun = 0;
        index += delimiter - 1;
      }
    }
    if (mathStart !== null) protect(mathStart, value.length);
    ranges.sort(function (left, right) { return left[0] - right[0] || left[1] - right[1]; });
    var merged = [];
    ranges.forEach(function (range) {
      var previous = merged[merged.length - 1];
      if (previous && range[0] <= previous[1]) {
        previous[1] = Math.max(previous[1], range[1]);
      } else {
        merged.push(range.slice());
      }
    });
    return merged;
  }

  function glossarySurfaceBoundaryIsSafe(markdown, start, end, surface) {
    var asciiWord = /[A-Za-z0-9_]/;
    if (asciiWord.test(surface.charAt(0)) && start > 0 &&
      asciiWord.test(markdown.charAt(start - 1))) return false;
    if (asciiWord.test(surface.charAt(surface.length - 1)) && end < markdown.length &&
      asciiWord.test(markdown.charAt(end))) return false;
    return true;
  }

  function glossaryMentionCandidate(
    entry, fragment, start, end, surface, structured, evidenceRank
  ) {
    var anchor = fragment && fragment.anchor;
    return {
      entry_id: glossaryEntryId(entry),
      markdown_start: start,
      markdown_end: end,
      surface: surface,
      _structured: structured === true,
      _evidence_rank: Number.isSafeInteger(evidenceRank) ? evidenceRank :
        structured === true ? 2 : 0,
      _anchor_match: Boolean(
        anchor && typeof anchor.target_id === "string" &&
        Array.isArray(entry && entry.anchor_ids) &&
        entry.anchor_ids.indexOf(anchor.target_id) >= 0
      ),
      _source_length: glossarySourceTerm(entry).normalize("NFC").trim().length
    };
  }

  function glossaryMentionCandidateWins(left, right, preferredEntryId) {
    if (left._evidence_rank !== right._evidence_rank) {
      return left._evidence_rank > right._evidence_rank;
    }
    var leftPreferred = left.entry_id === preferredEntryId;
    var rightPreferred = right.entry_id === preferredEntryId;
    if (leftPreferred !== rightPreferred) return leftPreferred;
    if (left._structured !== right._structured) return left._structured;
    if (left._anchor_match !== right._anchor_match) return left._anchor_match;
    if (left._source_length !== right._source_length) {
      return left._source_length > right._source_length;
    }
    return left.entry_id.localeCompare(right.entry_id) <= 0;
  }

  function resolveGlossaryMentionCandidates(candidates, preferredEntryId) {
    candidates.sort(function (left, right) {
      return left.markdown_start - right.markdown_start ||
        right.markdown_end - left.markdown_end ||
        left.entry_id.localeCompare(right.entry_id);
    });
    var ambiguous = new Set();
    var ambiguousEntryIds = new Set();
    var shadowed = new Set();
    for (var leftIndex = 0; leftIndex < candidates.length; leftIndex += 1) {
      for (var rightIndex = leftIndex + 1; rightIndex < candidates.length; rightIndex += 1) {
        if (candidates[rightIndex].markdown_start >= candidates[leftIndex].markdown_end) break;
        var left = candidates[leftIndex];
        var right = candidates[rightIndex];
        var sameRange =
          left.markdown_start === right.markdown_start &&
          left.markdown_end === right.markdown_end;
        if (sameRange) {
          if (glossaryMentionCandidateWins(left, right, preferredEntryId)) {
            shadowed.add(rightIndex);
          } else {
            shadowed.add(leftIndex);
          }
          continue;
        }
        var leftContainsRight =
          left.markdown_start <= right.markdown_start &&
          left.markdown_end >= right.markdown_end;
        var rightContainsLeft =
          right.markdown_start <= left.markdown_start &&
          right.markdown_end >= left.markdown_end;
        if (leftContainsRight) {
          shadowed.add(rightIndex);
        } else if (rightContainsLeft) {
          shadowed.add(leftIndex);
        } else {
          ambiguous.add(leftIndex);
          ambiguous.add(rightIndex);
          ambiguousEntryIds.add(left.entry_id);
          ambiguousEntryIds.add(right.entry_id);
        }
      }
    }
    var skipped = 0;
    var mentions = candidates.filter(function (_candidate, candidateIndex) {
      if (ambiguous.has(candidateIndex) || shadowed.has(candidateIndex)) skipped += 1;
      return !ambiguous.has(candidateIndex) && !shadowed.has(candidateIndex);
    }).map(function (candidate) {
      return {
        entry_id: candidate.entry_id,
        markdown_start: candidate.markdown_start,
        markdown_end: candidate.markdown_end,
        surface: candidate.surface
      };
    });
    return {
      mentions: mentions,
      skipped: skipped,
      ambiguous: ambiguous.size,
      ambiguous_entry_ids: Array.from(ambiguousEntryIds).sort()
    };
  }

  function buildGlossaryMentionIndex(
    fragment, markdown, entries, includeHistory, preferredEntryId
  ) {
    var value = normalizeMarkdown(markdown);
    if (!fragment || GLOSSARY_PROPAGATION_ROLES.indexOf(fragment.role) < 0 ||
      fragment.deleted === true) {
      return {mentions: [], skipped: 0, ambiguous: 0, ambiguous_entry_ids: []};
    }
    var protectedRanges = glossaryProtectedMarkdownRanges(value);
    var candidates = [];
    var skipped = 0;
    (entries || []).forEach(function (entry) {
      if (!glossaryEntryEditableInState(entry) ||
        !glossaryEntryTargetsFragment(entry, fragment)) {
        return;
      }
      var entryId = glossaryEntryId(entry);
      var current = glossaryTranslatedSurface(entry);
      var surfaces = includeHistory ? glossaryHistoricalSurfaces(entryId, current) :
        (current ? [current] : []);
      surfaces.forEach(function (surface) {
        var start = 0;
        while (surface && (start = value.indexOf(surface, start)) >= 0) {
          var end = start + surface.length;
          var protectedHit = protectedRanges.some(function (range) {
            return start < range[1] && range[0] < end;
          });
          if (protectedHit || !glossarySurfaceBoundaryIsSafe(value, start, end, surface)) {
            skipped += 1;
          } else {
            candidates.push(glossaryMentionCandidate(
              entry, fragment, start, end, surface, false
            ));
          }
          start = end;
        }
      });
    });
    var resolved = resolveGlossaryMentionCandidates(candidates, preferredEntryId);
    resolved.skipped += skipped;
    return resolved;
  }

  function validateStoredGlossaryMentions(fragment, markdown, entries) {
    var provenance = fragment && fragment.provenance || {};
    var hasSchema = Object.prototype.hasOwnProperty.call(
      provenance, "glossary_mentions_schema"
    );
    var hasMentions = Object.prototype.hasOwnProperty.call(
      provenance, "glossary_mentions"
    );
    if (!hasSchema && !hasMentions) return null;
    if (provenance.glossary_mentions_schema !== GLOSSARY_MENTIONS_SCHEMA ||
      !Array.isArray(provenance.glossary_mentions)) {
      throw new Error("fragment glossary mention index is invalid");
    }
    var value = normalizeMarkdown(markdown);
    var entriesById = new Map((entries || []).map(function (entry) {
      return [glossaryEntryId(entry), entry];
    }));
    var previousEnd = -1;
    var mentions = provenance.glossary_mentions.map(function (mention) {
      requireExactObject(mention, [
        "entry_id", "markdown_start", "markdown_end", "surface"
      ], "fragment glossary mention");
      var entry = entriesById.get(mention.entry_id);
      if (!entry || !glossaryEntryTargetsFragment(entry, fragment) ||
        !Number.isSafeInteger(mention.markdown_start) || mention.markdown_start < 0 ||
        !Number.isSafeInteger(mention.markdown_end) ||
        mention.markdown_end <= mention.markdown_start ||
        typeof mention.surface !== "string" || !mention.surface ||
        mention.markdown_start < previousEnd ||
        value.slice(mention.markdown_start, mention.markdown_end) !== mention.surface) {
        throw new Error("fragment glossary mention index does not match its Markdown");
      }
      previousEnd = mention.markdown_end;
      return JSON.parse(JSON.stringify(mention));
    });
    return {
      mentions: mentions,
      skipped: 0,
      ambiguous: 0,
      ambiguous_entry_ids: []
    };
  }

  function fragmentGlossaryMentions(fragment, entries, preferredEntryId) {
    /* Persisted ranges keep their owner; structured and fallback evidence may
       add only ranges that do not displace that durable assignment. */
    var stored = validateStoredGlossaryMentions(
      fragment, fragment.markdown_body, entries
    );
    var explicit = explicitGlossaryMentions(fragment, entries);
    var fallback = buildGlossaryMentionIndex(
      fragment,
      fragment.markdown_body,
      (entries || []).filter(function (entry) {
        return !explicit.entryIds.has(glossaryEntryId(entry));
      }),
      true,
      preferredEntryId
    );
    var entriesById = new Map((entries || []).map(function (entry) {
      return [glossaryEntryId(entry), entry];
    }));
    var combined = resolveGlossaryMentionCandidates(
      (stored ? stored.mentions.map(function (mention) {
        return glossaryMentionCandidate(
          entriesById.get(mention.entry_id), fragment,
          mention.markdown_start, mention.markdown_end, mention.surface, true, 3
        );
      }) : []).concat(explicit.candidates, fallback.mentions.map(function (mention) {
        return glossaryMentionCandidate(
          entriesById.get(mention.entry_id), fragment,
          mention.markdown_start, mention.markdown_end, mention.surface, false
        );
      })),
      preferredEntryId
    );
    var ambiguousEntryIds = new Set(fallback.ambiguous_entry_ids);
    combined.ambiguous_entry_ids.forEach(function (entryId) {
      ambiguousEntryIds.add(entryId);
    });
    return {
      mentions: combined.mentions,
      skipped: fallback.skipped + combined.skipped,
      ambiguous: fallback.ambiguous + combined.ambiguous,
      ambiguous_entry_ids: Array.from(ambiguousEntryIds).sort()
    };
  }

  function explicitGlossaryMentions(fragment, entries) {
    var candidates = [];
    var entryIds = new Set();
    var markdown = normalizeMarkdown(fragment.markdown_body);
    (entries || []).forEach(function (entry) {
      if (!validGlossarySurfaceAnchors(entry) ||
        !glossaryEntryTargetsFragment(entry, fragment)) return;
      var matched = (entry.surface_anchors || []).filter(function (anchor) {
        return anchor.fragment_id === fragment.fragment_id &&
          anchor.fragment_semantic_digest === fragment.semantic_digest &&
          anchor.block_id === fragment.anchor.target_id;
      });
      if (!matched.length) return;
      entryIds.add(glossaryEntryId(entry));
      matched.forEach(function (anchor) {
        if (markdown.slice(anchor.markdown_start, anchor.markdown_end) !== anchor.surface) {
          throw new Error("structured glossary mention does not match its Fragment");
        }
        candidates.push(glossaryMentionCandidate(
          entry, fragment, anchor.markdown_start, anchor.markdown_end,
          anchor.surface, true
        ));
      });
    });
    return {candidates: candidates, entryIds: entryIds};
  }

  function updateGlossaryMentionProvenance(
    provenance, metadata, markdown, entries, preferredEntryId
  ) {
    delete provenance.glossary_mentions_schema;
    delete provenance.glossary_mentions;
    if (GLOSSARY_PROPAGATION_ROLES.indexOf(metadata.role) < 0 ||
      metadata.deleted === true) {
      return {mentions: [], skipped: 0, ambiguous: 0, ambiguous_entry_ids: []};
    }
    var indexed = buildGlossaryMentionIndex(
      metadata, markdown, entries, false, preferredEntryId
    );
    provenance.glossary_mentions_schema = GLOSSARY_MENTIONS_SCHEMA;
    provenance.glossary_mentions = indexed.mentions;
    return indexed;
  }

  function initialGlossaryRevisions() {
    var publication = state.payload.publication;
    state.embeddedGlossaryRevisions = (state.payload.glossary_revisions || []).slice();
    state.glossaryBase = JSON.parse(JSON.stringify(publication.glossary || []));
    publication.glossary = JSON.parse(JSON.stringify(state.glossaryBase));
    var entryCounts = new Map();
    state.glossaryBase.forEach(function (entry) {
      var entryId = glossaryEntryId(entry);
      if (entryId) entryCounts.set(entryId, (entryCounts.get(entryId) || 0) + 1);
    });
    state.glossaryDuplicateIds = new Set(Array.from(entryCounts).filter(
      function (item) { return item[1] > 1; }
    ).map(function (item) { return item[0]; }));
    state.glossaryBaseDigests = new Map();
    state.glossaryRevisions = new Map();
    state.glossaryRevisionDigests = new Map();
    state.selectedGlossary = new Map();
    state.selectedGlossaryRevisions = new Map();
    state.glossaryDiagnostics = [];
    state.glossaryFileDiagnostics = [];
    state.embeddedGlossaryRevisions.forEach(addGlossaryRevision);
  }

  async function prepareGlossary() {
    initialGlossaryRevisions();
    var suppliedDigests = state.payload.glossary_base_digests || {};
    for (var index = 0; index < state.glossaryBase.length; index += 1) {
      var entry = state.glossaryBase[index];
      var entryId = glossaryEntryId(entry);
      if (!entryId || state.glossaryDuplicateIds.has(entryId) ||
        !glossaryEntryHasEditableShape(entry)) continue;
      var supplied = suppliedDigests[entryId];
      if (digestValue(supplied)) {
        state.glossaryBaseDigests.set(entryId, supplied);
      } else if (glossaryEntryIsEditable(entry)) {
        state.glossaryBaseDigests.set(entryId, await canonicalDigest(
          glossaryBaseMaterial(entry)
        ));
      }
    }
    resolveGlossaryAll();
    captureInitialGlossarySelection();
  }

  function addGlossaryRevision(raw) {
    addGlossaryRevisionTo(
      raw,
      state.glossaryRevisions,
      state.glossaryFileDiagnostics,
      state.glossaryRevisionDigests
    );
  }

  function addGlossaryRevisionTo(raw, revisions, diagnostics, revisionDigests) {
    var revision = raw && raw.entry ? Object.assign({}, raw) : null;
    if (!revision) return;
    var digest = revision.semantic_digest;
    var origin = revision._origin;
    delete revision.semantic_digest;
    delete revision._origin;
    try {
      validateGlossaryRevisionMetadata(revision);
      if (!digestValue(digest)) {
        throw new Error("glossary revision semantic digest is invalid");
      }
    } catch (error) {
      diagnostics.push(
        "Ignored invalid glossary revision " + (revision.entry_id || "(unknown)") + ": " +
        String(error.message || error)
      );
      return;
    }
    revision.semantic_digest = digest;
    if (origin) revision._origin = origin;
    var values = revisions.get(revision.entry_id) || [];
    var digests = revisionDigests.get(revision.entry_id) || new Set();
    if (digests.has(revision.semantic_digest)) return;
    values.push(revision);
    digests.add(revision.semantic_digest);
    revisions.set(revision.entry_id, values);
    revisionDigests.set(revision.entry_id, digests);
  }

  function glossaryBaseEntry(entryId) {
    return state.glossaryBase.find(function (entry) {
      return glossaryEntryId(entry) === entryId;
    }) || null;
  }

  function resolveGlossaryAll() {
    state.selectedGlossary = new Map();
    state.selectedGlossaryRevisions = new Map();
    var diagnostics = state.glossaryFileDiagnostics.slice();
    state.glossaryBase.forEach(function (base) {
      var entryId = glossaryEntryId(base);
      if (!entryId) return;
      if (state.glossaryDuplicateIds.has(entryId)) {
        var duplicateDiagnostic =
          "Publication repeats glossary entry ID: " + entryId;
        if (diagnostics.indexOf(duplicateDiagnostic) < 0) {
          diagnostics.push(duplicateDiagnostic);
        }
        return;
      }
      var baseDigest = state.glossaryBaseDigests.get(entryId);
      if (!baseDigest) {
        state.selectedGlossary.set(entryId, base);
        state.selectedGlossaryRevisions.set(entryId, null);
        return;
      }
      var values = state.glossaryRevisions.get(entryId) || [];
      var byDigest = new Map();
      values.forEach(function (revision) {
        if (validGlossaryRevisionChange(base, revision.entry)) {
          byDigest.set(revision.semantic_digest, revision);
        } else {
          diagnostics.push(
            "Ignored glossary revision with immutable field changes: " + entryId
          );
        }
      });
      var children = new Map();
      byDigest.forEach(function (revision) {
        var parent = revision.parent_semantic_digest;
        var parentRevision = parent === baseDigest ? null : byDigest.get(parent);
        var expected = parent === baseDigest ? 2 :
          parentRevision ? parentRevision.revision + 1 : null;
        if (expected === null) {
          diagnostics.push("Ignored dangling glossary revision: " + entryId + " v" + revision.revision);
          return;
        }
        if (revision.revision !== expected) {
          diagnostics.push("Ignored nonlinear glossary revision: " + entryId + " v" + revision.revision);
          return;
        }
        var list = children.get(parent) || [];
        list.push(revision);
        children.set(parent, list);
      });
      var selected = null;
      var parentDigest = baseDigest;
      while (true) {
        var next = (children.get(parentDigest) || []).filter(function (item) {
          return byDigest.has(item.semantic_digest);
        });
        if (!next.length) break;
        if (next.length > 1) {
          var equivalent = equivalentGlossaryChild(next, children);
          if (!equivalent) {
            diagnostics.push("Glossary revision fork for " + entryId + "; common parent retained.");
            break;
          }
          diagnostics.push(
            "Equivalent glossary revision retries for " + entryId +
            "; selected one deterministic copy."
          );
          next = [equivalent];
        }
        selected = next[0];
        parentDigest = selected.semantic_digest;
      }
      state.selectedGlossary.set(entryId, selected ? selected.entry : base);
      state.selectedGlossaryRevisions.set(entryId, selected);
    });
    state.glossaryDiagnostics = diagnostics;
    state.payload.publication.glossary = state.glossaryBase.map(function (base) {
      var entryId = glossaryEntryId(base);
      return state.glossaryDuplicateIds.has(entryId) ? base :
        state.selectedGlossary.get(entryId) || base;
    });
  }

  function equivalentGlossaryChild(children, descendants) {
    if (!children.length) return null;
    if (!children.every(function (revision) {
      return jsonValuesEqual(revision.entry, children[0].entry);
    })) return null;
    var continued = descendants ? children.filter(function (revision) {
      return (descendants.get(revision.semantic_digest) || []).length > 0;
    }) : [];
    if (continued.length === 1) return continued[0];
    if (continued.length > 1) return null;
    return children.slice().sort(function (left, right) {
      return left.semantic_digest.localeCompare(right.semantic_digest);
    })[0];
  }

  function selectedGlossaryDigest(entryId) {
    var revision = state.selectedGlossaryRevisions.get(entryId);
    return revision ? revision.semantic_digest : state.glossaryBaseDigests.get(entryId) || "";
  }

  function captureInitialGlossarySelection() {
    state.initialGlossaryDigests = new Map();
    state.glossaryBase.forEach(function (entry) {
      var entryId = glossaryEntryId(entry);
      if (entryId) state.initialGlossaryDigests.set(entryId, selectedGlossaryDigest(entryId));
    });
  }

  function changedGlossaryEntries() {
    return state.glossaryBase.map(function (entry) {
      var entryId = glossaryEntryId(entry);
      return {
        entry: state.selectedGlossary.get(entryId) || entry,
        entryId: entryId,
        digest: selectedGlossaryDigest(entryId)
      };
    }).filter(function (item) {
      return item.entryId && state.initialGlossaryDigests.get(item.entryId) !== item.digest &&
        glossaryEntryEditableInState(item.entry);
    });
  }

  function glossaryRevisionState() {
    var records = [];
    state.glossaryRevisions.forEach(function (values) {
      values.slice().sort(function (left, right) {
        return left.revision - right.revision ||
          left.semantic_digest.localeCompare(right.semantic_digest);
      }).forEach(function (revision) {
        records.push(Object.assign({}, glossaryRevisionMaterial(revision), {
          semantic_digest: revision.semantic_digest
        }));
      });
    });
    records.sort(function (left, right) {
      return left.entry_id.localeCompare(right.entry_id) ||
        left.revision - right.revision ||
        left.semantic_digest.localeCompare(right.semantic_digest);
    });
    var selected = [];
    state.glossaryBase.forEach(function (entry) {
      var revision = state.selectedGlossaryRevisions.get(glossaryEntryId(entry));
      if (revision) selected.push(revision.semantic_digest);
    });
    return {
      revisions: records,
      selected_revision_digests: selected
    };
  }

  function projectGlossaryMarkdown(markdown, fragment) {
    var value = normalizeMarkdown(markdown);
    var edits = [];
    var digest = fragment && fragment.semantic_digest;
    if (!digest || !fragment.fragment_id) return normalizeMarkdown(markdown);
    (state.payload.publication.glossary || []).forEach(function (entry) {
      if (!validGlossarySurfaceAnchors(entry)) return;
      var translatedKey = glossaryTranslatedKey(entry);
      var nextSurface = translatedKey ? String(entry[translatedKey] || "") : "";
      (Array.isArray(entry.surface_anchors) ? entry.surface_anchors : []).forEach(function (anchor) {
        if (!anchor || anchor.fragment_id !== fragment.fragment_id ||
          anchor.fragment_semantic_digest !== digest ||
          anchor.block_id !== fragmentTargetId(fragment) ||
          !Number.isSafeInteger(anchor.markdown_start) ||
          !Number.isSafeInteger(anchor.markdown_end) ||
          anchor.markdown_start < 0 || anchor.markdown_end <= anchor.markdown_start ||
          anchor.markdown_end > value.length ||
          typeof anchor.surface !== "string" ||
          value.slice(anchor.markdown_start, anchor.markdown_end) !== anchor.surface ||
          !nextSurface) return;
        edits.push({start: anchor.markdown_start, end: anchor.markdown_end, value: nextSurface});
      });
    });
    edits.sort(function (left, right) { return right.start - left.start || right.end - left.end; });
    for (var index = 0; index < edits.length; index += 1) {
      if (index > 0 && edits[index].end > edits[index - 1].start) {
        return normalizeMarkdown(markdown);
      }
    }
    edits.forEach(function (edit) {
      value = value.slice(0, edit.start) + edit.value + value.slice(edit.end);
    });
    return value;
  }

  function initialRevisions() {
    ensureSourceIndexes();
    state.embeddedRevisions = (state.payload.revisions || []).slice();
    state.activeFragmentIds = new Set(state.embeddedRevisions.map(function (raw) {
      return raw.metadata ? raw.metadata.fragment_id : raw.fragment_id;
    }));
    resetRevisionState();
    resolveAll();
  }

  function resetRevisionState() {
    state.revisions = new Map();
    state.revisionDigests = new Map();
    state.fileDiagnostics = [];
    state.embeddedRevisions.forEach(addRevision);
  }

  function addRevision(raw) {
    addRevisionTo(
      raw, state.revisions, state.fileDiagnostics, state.revisionDigests
    );
  }

  function addRevisionTo(raw, revisions, fileDiagnostics, revisionDigests) {
    var revision = raw.metadata ? Object.assign({}, raw.metadata) : Object.assign({}, raw);
    revision.markdown_body = raw.markdown_body === undefined ?
      revision.markdown_body || "" : raw.markdown_body;
    revision.semantic_digest = raw.semantic_digest || revision.semantic_digest || "";
    revision._origin = raw._origin || "embedded";
    try {
      validateRevisionMetadata(metadataOnly(revision));
    } catch (error) {
      fileDiagnostics.push(
        "Ignored invalid fragment " + (revision.fragment_id || "(unknown)") + ": " +
        String(error.message || error)
      );
      return;
    }
    var values = revisions.get(revision.fragment_id) || [];
    var digests = revisionDigests && (
      revisionDigests.get(revision.fragment_id) || new Set()
    );
    if (!digests || !digests.has(revision.semantic_digest)) {
      values.push(revision);
      revisions.set(revision.fragment_id, values);
      if (digests) {
        digests.add(revision.semantic_digest);
        revisionDigests.set(revision.fragment_id, digests);
      }
    }
  }

  function resolveAll() {
    state.selected.clear();
    state.resolutionDiagnostics = new Map();
    state.revisions.forEach(function (values, fragmentId) {
      resolveFragmentInState(fragmentId, values);
    });
    rebuildDiagnostics();
    syncAppearanceGroups();
  }

  function resolveOne(fragmentId) {
    resolveFragmentInState(fragmentId, state.revisions.get(fragmentId) || []);
    rebuildDiagnostics();
    syncAppearanceGroups();
  }

  function resolveFragmentInState(fragmentId, values) {
    state.selected.delete(fragmentId);
    state.resolutionDiagnostics.delete(fragmentId);
    if (
      !state.activeFragmentIds.has(fragmentId) &&
      !browserCreatedHistory(values)
    ) {
      return;
    }
    var resolved = resolveFragment(values, fragmentId);
    if (resolved.selected) state.selected.set(fragmentId, resolved.selected);
    state.resolutionDiagnostics.set(fragmentId, resolved.diagnostics);
  }

  function rebuildDiagnostics() {
    state.diagnostics = (state.payload.diagnostics || []).slice().concat(
      state.fileDiagnostics
    );
    state.diagnostics = state.diagnostics.concat(state.glossaryDiagnostics);
    state.resolutionDiagnostics.forEach(function (values) {
      state.diagnostics = state.diagnostics.concat(values);
    });
    state.diagnostics = state.diagnostics.concat(anchorDiagnostics());
  }

  function anchorDiagnostics() {
    var diagnostics = [];
    state.selected.forEach(function (fragment) {
      if (!fragmentIsVisible(fragment)) return;
      if (!fragmentTargetId(fragment)) {
        diagnostics.push(
          "Fragment " + fragment.fragment_id + " has an unknown anchor."
        );
      }
    });
    return diagnostics;
  }

  function browserCreatedHistory(values) {
    var roots = values.filter(function (item) {
      return item.revision === 1 && item.parent_semantic_digest === null;
    });
    roots = Array.from(new Map(roots.map(function (item) {
      return [item.semantic_digest, item];
    })).values());
    return roots.length === 1 &&
      roots[0].provenance &&
      roots[0].provenance.producer === "alc-render-browser";
  }

  function resolveFragment(values, fragmentId) {
    var diagnostics = [];
    var byDigest = new Map();
    var childrenByParent = new Map();
    values.forEach(function (item) {
      if (item.semantic_digest) byDigest.set(item.semantic_digest, item);
      if (item.revision <= 1 || !item.parent_semantic_digest) return;
      var children = childrenByParent.get(item.parent_semantic_digest) || new Map();
      children.set(item.semantic_digest, item);
      childrenByParent.set(item.parent_semantic_digest, children);
    });
    var roots = values.filter(function (item) {
      return item.revision === 1 && item.parent_semantic_digest === null;
    });
    var uniqueRoots = Array.from(new Map(roots.map(function (item) {
      return [item.semantic_digest, item];
    })).values());
    if (uniqueRoots.length !== 1) {
      diagnostics.push(
        "Fragment " + fragmentId + " has " + uniqueRoots.length +
        " initial revisions; no revision was selected."
      );
      return {selected: null, diagnostics: diagnostics, conflicted: true};
    }
    var current = uniqueRoots[0];
    var conflicted = false;
    while (true) {
      var children = Array.from(
        (childrenByParent.get(current.semantic_digest) || new Map()).values()
      ).filter(function (item) {
        return item.revision === current.revision + 1;
      });
      if (children.length === 0) break;
      if (children.length > 1) {
        diagnostics.push(
          "Fragment " + fragmentId + " forks after revision " +
          current.revision + "; the common parent remains visible."
        );
        conflicted = true;
        break;
      }
      if (
        stableStringify(children[0].source) !== stableStringify(current.source) ||
        stableStringify(children[0].anchor) !== stableStringify(current.anchor)
      ) {
        diagnostics.push(
          "Fragment " + fragmentId +
          " changes its immutable source or anchor at revision " +
          children[0].revision + "."
        );
        conflicted = true;
        break;
      }
      current = children[0];
    }
    values.forEach(function (item) {
      if (item.revision > 1 && !byDigest.has(item.parent_semantic_digest)) {
        diagnostics.push(
          "Fragment " + fragmentId + " contains dangling revision " +
          item.revision + "."
        );
      }
    });
    return {
      selected: current,
      diagnostics: diagnostics,
      conflicted: conflicted
    };
  }

  function updatePrimaryTitleState(documentValue) {
    var titlePromotion = primaryTitlePromotion(documentValue);
    state.primaryTitleBlockId = titlePromotion ?
      titlePromotion.block.block_id : "";
    state.primaryTitleFragmentId = titlePromotion ?
      titlePromotion.fragment.fragment_id : "";
    document.body.dataset.alcPrimaryTitleBlockId = state.primaryTitleBlockId;
    document.body.dataset.alcPrimaryTitleFragmentId =
      state.primaryTitleFragmentId;
    return titlePromotion;
  }

  function renderBookHeader(documentValue) {
    var publication = state.payload.publication;
    var profile = publication.reader_profile || {};
    var title = readerTitle();
    document.title = title;
    document.documentElement.lang = targetLanguage() ||
      profile.source_language || "und";
    var titlePromotion = updatePrimaryTitleState(documentValue);
    var header = document.getElementById("alc-book-header");
    header.replaceChildren();
    var heading = element("h1", "", title);
    removeVisibleHtmlTags(heading);
    header.appendChild(heading);
    decorateGlossary(heading, "source");
    decorateGlossary(heading, "target");
    var delivery = renderDeliverySummary();
    if (delivery) header.appendChild(delivery);
    if (titlePromotion) {
      var translatedTitle = renderFragment(titlePromotion.fragment);
      translatedTitle.classList.add("alc-translated-title");
      translatedTitle.lang = titlePromotion.fragment.language ||
        profile.target_language || document.documentElement.lang;
      header.appendChild(translatedTitle);
    }
    var frontMatter = sourceFrontMatterEntries(documentValue);
    var promotedFrontMatter = frontMatter.filter(
      function (entry) {
        return sourceFrontMatterPromotedToHeader(documentValue, entry);
      }
    );
    promotedFrontMatter.forEach(function (entry) {
      header.appendChild(renderSourceFrontMatter(entry));
    });
    if (!frontMatter.length && Array.isArray(profile.authors) && profile.authors.length) {
      header.appendChild(element("p", "alc-authors", profile.authors.join(", ")));
    }
  }

  function deliveryLedger() {
    var profile = state.payload && state.payload.publication &&
      state.payload.publication.reader_profile || {};
    var ledger = state.payload && state.payload.delivery_ledger ||
      profile.delivery_ledger;
    if (!ledger || ledger.schema_version !== "alc.companion.delivery_ledger.v1" ||
      !Array.isArray(ledger.issues)) return null;
    return ledger;
  }

  function renderDeliverySummary() {
    var ledger = deliveryLedger();
    if (
      !ledger || ledger.delivery_grade === "complete" ||
      document.body.dataset.alcExportSnapshot === "true"
    ) return null;
    var chinese = targetLanguage().toLowerCase().indexOf("zh") === 0;
    var counts = new Map();
    ledger.issues.forEach(function (issue) {
      var category = String(issue && issue.category || "other");
      counts.set(category, (counts.get(category) || 0) + 1);
    });
    var panel = element("aside", "alc-delivery-summary");
    panel.dataset.deliveryGrade = ledger.delivery_grade;
    panel.dataset.deliveryIssueCount = String(ledger.issues.length);
    panel.setAttribute("aria-labelledby", "alc-delivery-summary-title");
    var header = element("header", "alc-delivery-summary-header");
    var title = element(
      "h2", "alc-delivery-summary-title",
      chinese ? "质量状态" : "Quality status"
    );
    title.id = "alc-delivery-summary-title";
    header.appendChild(title);
    var close = iconButton(
      "alc-delivery-summary-close", "", labels().close
    );
    close.innerHTML = speechIcon("close");
    close.addEventListener("click", function () {
      panel.hidden = true;
    });
    header.appendChild(close);
    panel.appendChild(header);
    panel.appendChild(element(
      "p", "",
      chinese ?
        "部分内容采用了安全降级；原文和完整审计记录均已保留。" :
        "Some content used a safe fallback; source and the complete audit record are preserved."
    ));
    var categoryLabels = new Map([
      ["translation_source_text", chinese ? "处保留原文" : "source-text fallbacks"],
      ["translation_review_skipped", chinese ? "处使用审阅前译文" : "pre-review translations"],
      ["glossary_omitted", chinese ? "个术语未显示" : "omitted glossary terms"]
    ]);
    var list = element("ul", "alc-delivery-summary-list");
    var known = 0;
    categoryLabels.forEach(function (label, category) {
      var count = counts.get(category) || 0;
      if (!count) return;
      known += count;
      list.appendChild(element("li", "", String(count) + " " + label));
    });
    var other = ledger.issues.length - known;
    if (other > 0) {
      list.appendChild(element(
        "li", "", String(other) + " " +
          (chinese ? "项其他降级" : "other fallback items")
      ));
    }
    panel.appendChild(list);
    return panel;
  }

  function deliveryIssueForBlock(blockId) {
    var ledger = deliveryLedger();
    if (!ledger) return null;
    var direct = ledger.issues.find(function (item) {
      return item && item.scope === blockId;
    });
    if (direct) return direct;
    var blocks = state.payload.publication.source_document.blocks || [];
    var index = blocks.findIndex(function (item) { return item.block_id === blockId; });
    var outline = state.payload.publication.outline || [];
    var chapter = outline.find(function (item) {
      return item && item.level === 1 && index >= item.block_start && index < item.block_end;
    });
    return chapter ? ledger.issues.find(function (item) {
      return item && item.scope === chapter.section_id;
    }) || null : null;
  }

  function markDeliveryState(row, blockId) {
    var issue = deliveryIssueForBlock(blockId);
    if (!issue) return;
    row.dataset.deliveryCategory = String(issue.category || "fallback");
    if (
      issue.source_preserved === true &&
      String(issue.category).indexOf("translation_") === 0
    ) {
      row.classList.add("alc-source-text-fallback");
    }
  }

  function syncPromotedTitleSurface() {
    if (!state.payload || !state.fragmentGroups) return;
    if (
      typeof document.querySelector !== "function" ||
      !document.querySelector("#alc-book-header")
    ) return;
    renderBookHeader(state.payload.publication.source_document);
  }

  function renderReader() {
    stopProgressiveRendering();
    state.bibliographyIndexCache = null;
    state.glossarySurfaceCache = {source: null, target: null};
    var publication = state.payload.publication;
    var documentValue = publication.source_document;
    var strings = labels();

    state.sourceBibliographyIndex = buildSourceBibliographyIndex(
      state.payload.legacy_bibliography_targets || [],
      documentValue.blocks || []
    );
    state.sourceStructuralIndex = buildSourceStructuralIndex(
      state.payload.legacy_structural_targets || [],
      documentValue.blocks || []
    );
    state.sourceNoteIndex = buildSourceNoteIndex(documentValue);
    state.sourceInternalLinkIndex = buildSourceInternalLinkIndex(
      state.sourceBibliographyIndex,
      state.sourceStructuralIndex,
      state.sourceNoteIndex
    );

    loadPayloadForBlockRange(0, 1);
    state.fragmentGroups = groupedFragments(documentValue);
    renderBookHeader(documentValue);

    var main = document.getElementById("ac-document");
    var contents = document.getElementById("alc-contents-list");
    main.replaceChildren();
    contents.replaceChildren();

    state.renderPlan = buildRenderChunks(
      documentValue.blocks || [], publication.outline || []
    );
    state.renderedChunkIds = new Set();
    state.chunkNodes = new Map();
    state.chunkByTargetId = new Map();
    state.diagnosticsRoot = element("div", "alc-reader-diagnostics");
    main.appendChild(state.diagnosticsRoot);
    renderDiagnostics(state.diagnosticsRoot);
    state.visibilityEmptyRoot = element(
      "p", "alc-visibility-empty", strings.noVisibleContent
    );
    state.visibilityEmptyRoot.hidden = true;
    main.appendChild(state.visibilityEmptyRoot);

    state.renderPlan.forEach(function (chunk) {
      var node = element("div", "alc-render-chunk");
      node.dataset.chunkId = chunk.chunk_id;
      node.dataset.chunkKind = chunk.kind;
      node.setAttribute("aria-busy", "true");
      node.style.setProperty(
        "--alc-chunk-placeholder-height",
        String(chunkHeightEstimate(chunk)) + "px"
      );
      state.chunkNodes.set(chunk.chunk_id, node);
      main.appendChild(node);
      if (chunk.kind === "content") {
        for (
          var index = chunk.block_start;
          index < chunk.block_end;
          index += 1
        ) {
          var block = documentValue.blocks[index];
          state.chunkByTargetId.set(
            "block-" + safeToken(block.block_id), chunk
          );
          if (block.kind === "heading") {
            state.chunkByTargetId.set(
              "heading-" + safeToken(block.block_id), chunk
            );
          }
          if (state.sourceBibliographyIndex.blockIds.has(block.block_id)) {
            state.sourceBibliographyIndex.itemIndexesByBlockId.get(
              block.block_id
            ).forEach(
              function (itemIndex) {
                state.chunkByTargetId.set(
                  sourceReferenceTargetId(block.block_id, itemIndex), chunk
                );
              }
            );
          }
        }
      }
    });
    var presentationIndex = sourcePresentationIndex(documentValue);
    if (presentationIndex) {
      presentationIndex.classificationByHeading.forEach(function (relation) {
        var headingTarget = "block-" + safeToken(relation.heading_block_id);
        var headingChunk = state.chunkByTargetId.get(headingTarget);
        if (!headingChunk) {
          throw new Error("source classification render chunk is missing");
        }
        relation.value_block_ids.forEach(function (blockId) {
          state.chunkByTargetId.set("block-" + safeToken(blockId), headingChunk);
        });
      });
    }
    registerSourceNoteNavigationTargets(documentValue);
    var appendix = state.renderPlan.find(function (chunk) {
      return chunk.kind === "appendices";
    });
    if (appendix) {
      state.chunkByTargetId.set("alc-glossary", appendix);
      state.chunkByTargetId.set("alc-references", appendix);
    }

    renderContents(contents, publication.outline || [], strings);
    setupContents();
    setupProgressiveNavigation();
    setupPrintRendering();
    state.readerShellReady = true;

    var initialChunk = initialRenderChunk();
    state.hydrationOrder = hydrationOrderFrom(initialChunk);
    updateRenderComplete();
  }

  function primaryTitlePromotion(documentValue) {
    var block = (documentValue.blocks || []).find(function (candidate) {
      var payload = candidate && candidate.payload || {};
      return candidate && candidate.kind === "heading" &&
        Number(payload.level) === 1;
    });
    if (!block) return null;
    var candidates = (state.fragmentGroups.get(block.block_id) || []).slice();
    var known = new Set();
    state.selected.forEach(function (candidate) {
      if (fragmentTargetId(candidate) === block.block_id) {
        known.add(candidate.fragment_id);
      }
    });
    candidates.forEach(function (candidate) {
      known.add(candidate.fragment_id);
    });
    (state.payload.selected_heading_fragments || []).forEach(function (candidate) {
      if (
        candidate && candidate.target_id === block.block_id &&
        !known.has(candidate.fragment_id)
      ) {
        candidates.push(candidate);
        known.add(candidate.fragment_id);
      }
    });
    candidates.sort(function (left, right) {
      return Number(left.priority) - Number(right.priority) ||
        String(left.fragment_id).localeCompare(String(right.fragment_id));
    });
    var fragment = candidates.find(
      function (candidate) {
        return fragmentIsVisible(candidate) &&
          candidate.role === "translation" && candidate.priority <= 100;
      }
    );
    return fragment ? {block: block, fragment: fragment} : null;
  }

  function buildRenderChunks(blocks, outline) {
    var blockCount = blocks.length;
    var roots = (outline || []).filter(function (section) {
      return Array.isArray(section.path) && section.path.length === 1;
    });
    if (!roots.length && outline.length) {
      var minimumLevel = Math.min.apply(null, outline.map(function (section) {
        return Number(section.level);
      }));
      roots = outline.filter(function (section) {
        return Number(section.level) === minimumLevel;
      });
    }
    roots = roots.slice().sort(function (left, right) {
      return Number(left.block_start) - Number(right.block_start) ||
        Number(left.block_end) - Number(right.block_end) ||
        Number(left.ordinal || 0) - Number(right.ordinal || 0);
    });

    var ranges = [];
    var cursor = 0;
    roots.forEach(function (section) {
      var start = Math.max(0, Math.min(blockCount, Number(section.block_start)));
      var end = Math.max(start, Math.min(blockCount, Number(section.block_end)));
      if (start > cursor) ranges.push({start: cursor, end: start});
      if (end > cursor) {
        ranges.push({
          start: Math.max(cursor, start),
          end: end,
          title: section.title || null
        });
        cursor = end;
      }
    });
    if (cursor < blockCount) ranges.push({start: cursor, end: blockCount});
    if (!ranges.length && blockCount) ranges.push({start: 0, end: blockCount});

    var chunks = [];
    ranges.forEach(function (range) {
      var start = range.start;
      while (start < range.end) {
        var end = Math.min(range.end, start + MAX_BLOCKS_PER_RENDER_CHUNK);
        chunks.push({
          chunk_id: "chunk-" + String(chunks.length).padStart(4, "0"),
          kind: "content",
          block_start: start,
          block_end: end,
          title: start === range.start ? range.title || null : null
        });
        start = end;
      }
    });
    chunks.push({
      chunk_id: "chunk-" + String(chunks.length).padStart(4, "0"),
      kind: "appendices",
      block_start: blockCount,
      block_end: blockCount,
      title: null
    });
    return chunks;
  }

  function chunkHeightEstimate(chunk) {
    if (chunk.kind === "appendices") {
      var publication = state.payload.publication;
      return Math.max(
        320,
        ((publication.glossary || []).length +
          (publication.bibliography || []).length) * 72
      );
    }
    return Math.max(
      320,
      (chunk.block_end - chunk.block_start) * CHUNK_BLOCK_HEIGHT_ESTIMATE
    );
  }

  function initialRenderChunk() {
    var target = chunkForTargetId(hashTargetId(window.location.hash));
    if (target) {
      renderChunk(target);
      armHashCalibration(window.location.hash);
      return target;
    }
    var contentChunks = state.renderPlan.filter(function (chunk) {
      return chunk.kind === "content";
    });
    if (!contentChunks.length) {
      var appendix = state.renderPlan[0] || null;
      if (appendix) renderChunk(appendix);
      return appendix;
    }
    var renderedHeight = 0;
    var minimumHeight = Math.max(window.innerHeight * 1.5, 720);
    var last = contentChunks[0];
    for (var index = 0; index < contentChunks.length; index += 1) {
      last = contentChunks[index];
      var node = renderChunk(last);
      renderedHeight += node.getBoundingClientRect().height;
      if (renderedHeight >= minimumHeight) break;
    }
    return last;
  }

  function hydrationOrderFrom(initialChunk) {
    if (!state.renderPlan.length) return [];
    var initialIndex = Math.max(0, state.renderPlan.indexOf(initialChunk));
    if (initialIndex === 0) {
      return state.renderPlan.map(function (chunk) { return chunk.chunk_id; });
    }
    var values = [state.renderPlan[initialIndex].chunk_id];
    for (var distance = 1; values.length < state.renderPlan.length; distance += 1) {
      if (initialIndex + distance < state.renderPlan.length) {
        values.push(state.renderPlan[initialIndex + distance].chunk_id);
      }
      if (initialIndex - distance >= 0) {
        values.push(state.renderPlan[initialIndex - distance].chunk_id);
      }
    }
    return values;
  }

  function renderChunk(chunk) {
    if (!chunk) return null;
    var node = state.chunkNodes.get(chunk.chunk_id);
    if (!node) throw new Error("render chunk has no document shell");
    if (state.renderedChunkIds.has(chunk.chunk_id)) return node;
    if (chunk.kind === "content") {
      loadPayloadForBlockRange(chunk.block_start, chunk.block_end);
    }
    if (state.chunkObserver) state.chunkObserver.unobserve(node);
    renderChunkBody(chunk, node);
    node.classList.add("is-rendered");
    node.setAttribute("aria-busy", "false");
    state.renderedChunkIds.add(chunk.chunk_id);
    updateRenderComplete();
    recalibrateHashTarget();
    return node;
  }

  function rerenderChunk(chunk) {
    if (!chunk || !state.renderedChunkIds.has(chunk.chunk_id)) return;
    var node = state.chunkNodes.get(chunk.chunk_id);
    renderChunkBody(chunk, node);
  }

  function renderChunkBody(chunk, node) {
    var publication = state.payload.publication;
    var documentValue = publication.source_document;
    var content = document.createDocumentFragment();
    if (chunk.kind === "content") {
      for (
        var index = chunk.block_start;
        index < chunk.block_end;
        index += 1
      ) {
        sourceFrontMatterAt(documentValue, index).forEach(function (entry) {
          content.appendChild(renderSourceFrontMatter(entry));
        });
        var block = documentValue.blocks[index];
        if (isPdfPageMarkerBlock(block) || isStandaloneHtmlCommentBlock(block)) {
          continue;
        }
        documentNotesBefore(block.block_id).forEach(function (note) {
          content.appendChild(renderDocumentNote(note));
        });
        var classification = sourceClassificationForHeading(
          documentValue, block.block_id
        );
        if (classification) {
          loadPayloadForBlockRange(
            index, index + 1 + classification.value_block_ids.length
          );
          content.appendChild(renderSourceClassificationRow(classification));
          continue;
        }
        if (sourceClassificationForValue(documentValue, block.block_id)) continue;
        content.appendChild(renderSourceRow(
          block, state.fragmentGroups.get(block.block_id) || []
        ));
      }
      if (chunk.block_end === documentValue.blocks.length) {
        sourceFrontMatterAt(documentValue, documentValue.blocks.length).forEach(
          function (entry) { content.appendChild(renderSourceFrontMatter(entry)); }
        );
        documentNotesBefore(null).forEach(function (note) {
          content.appendChild(renderDocumentNote(note));
        });
      }
    } else {
      renderGlossary(content, publication.glossary || [], labels());
      renderBibliography(content, publication.bibliography || [], labels());
    }
    node.replaceChildren(content);
    decorateScrollableTables(node);
    applyVisibility(node);
    syncScrollableTables(node);
  }

  function renderAllChunks() {
    cancelIdleHydration();
    state.renderPlan.forEach(renderChunk);
    updateRenderComplete();
  }

  function refreshChangedSelections(previousSelected) {
    if (!state.readerShellReady) return;
    var fragmentIds = new Set(previousSelected.keys());
    state.selected.forEach(function (_revision, fragmentId) {
      fragmentIds.add(fragmentId);
    });
    var changedAnchors = [];
    fragmentIds.forEach(function (fragmentId) {
      var previous = previousSelected.get(fragmentId);
      var current = state.selected.get(fragmentId);
      if (
        (previous && previous.semantic_digest) ===
        (current && current.semantic_digest)
      ) {
        return;
      }
      if (previous && previous.anchor) changedAnchors.push(previous.anchor);
      if (current && current.anchor) changedAnchors.push(current.anchor);
    });
    if (changedAnchors.length) {
      state.fragmentGroups = groupedFragments(
        state.payload.publication.source_document
      );
      syncPromotedTitleSurface();
    }
    syncVisibilityRoles();
    renderDiagnostics(state.diagnosticsRoot);
    var chunks = new Set();
    changedAnchors.forEach(function (anchor) {
      var chunk = chunkForAnchor(anchor);
      if (chunk) chunks.add(chunk);
    });
    chunks.forEach(rerenderChunk);
  }

  function refreshGlossarySurfaces(previousGlossary) {
    if (!state.readerShellReady) return;
    var changed = state.selectedGlossary.size !== previousGlossary.size;
    state.selectedGlossary.forEach(function (entry, entryId) {
      if (previousGlossary.get(entryId) !== entry) changed = true;
    });
    if (!changed && !state.glossaryDiagnostics.length) return;
    state.glossarySurfaceCache = {source: null, target: null};
    var tooltip = document.getElementById("alc-tooltip");
    if (tooltip) {
      tooltip.hidden = true;
      tooltip.textContent = "";
    }
    syncPromotedTitleSurface();
    state.renderedChunkIds.forEach(function (chunkId) {
      rerenderChunk(state.renderPlan.find(function (chunk) {
        return chunk.chunk_id === chunkId;
      }));
    });
    renderDiagnostics(state.diagnosticsRoot);
  }

  function refreshChunkForAnchor(anchor) {
    if (!state.readerShellReady) return;
    renderDiagnostics(state.diagnosticsRoot);
    var chunk = chunkForAnchor(anchor);
    rerenderChunk(chunk);
  }

  function refreshFragmentGroup(fragmentId, anchor) {
    updateFragmentGroup(fragmentId, anchor);
    syncPromotedTitleSurface();
  }

  function updateFragmentGroup(fragmentId, anchor) {
    var target = fragmentTargetId({anchor: anchor});
    if (!target) return;
    var values = (state.fragmentGroups.get(target) || []).filter(function (item) {
      return item.fragment_id !== fragmentId;
    });
    var selected = state.selected.get(fragmentId);
    var documentValue = state.payload.publication.source_document;
    if (
      fragmentIsVisible(selected) &&
      !sourceNoteTranslationId(documentValue, selected)
    ) values.push(selected);
    values.sort(function (left, right) {
      return left.priority - right.priority ||
        left.fragment_id.localeCompare(right.fragment_id);
    });
    if (values.length) state.fragmentGroups.set(target, values);
    else state.fragmentGroups.delete(target);
  }

  function chunkForAnchor(anchor) {
    if (!anchor) return null;
    var target = anchor.target_id;
    if (anchor.kind === "section") {
      target = ensureSourceIndexes().sectionAnchors.get(target) || null;
    }
    return target ?
      state.chunkByTargetId.get("block-" + safeToken(target)) || null :
      null;
  }

  function chunkForTargetId(targetId) {
    if (!targetId) return null;
    targetId = canonicalReaderTargetId(targetId);
    if (targetId.indexOf("reference-") === 0) {
      return state.chunkByTargetId.get("alc-references") || null;
    }
    return state.chunkByTargetId.get(targetId) || null;
  }

  function sourceReferenceTargetId(blockId, itemIndex) {
    return "source-reference-" + safeToken(blockId) + "-" +
      String(itemIndex + 1);
  }

  function buildSourceBibliographyIndex(descriptors, blocks) {
    var empty = {
      blockId: "", blockIds: new Set(), aliases: new Map(),
      itemIndexes: new Set(), itemIndexesByBlockId: new Map()
    };
    if (descriptors === undefined) return empty;
    if (!Array.isArray(descriptors) || !Array.isArray(blocks)) {
      throw new Error("ALC reader legacy bibliography manifest is invalid");
    }
    var blocksById = new Map();
    blocks.forEach(function (block) {
      if (block && normalizedNonblank(block.block_id)) {
        blocksById.set(block.block_id, block);
      }
    });
    var blockIds = new Set();
    var aliases = new Map();
    var itemIndexes = new Set();
    var itemIndexesByBlockId = new Map();
    var targetIds = new Set();
    descriptors.forEach(function (descriptor) {
      var keys = descriptor && typeof descriptor === "object" ?
        Object.keys(descriptor).sort().join(",") : "";
      var aliasMatch = descriptor && typeof descriptor.alias === "string" ?
        /^bib[.]bib([1-9][0-9]*)$/.exec(descriptor.alias) : null;
      var block = descriptor ? blocksById.get(descriptor.block_id) : null;
      var items = block && block.payload && block.payload.items;
      var exactSplitItem = Boolean(descriptor && descriptor.item_index === 0);
      var ordinalItem = Boolean(
        aliasMatch && Number(aliasMatch[1]) === descriptor.item_index + 1
      );
      var targetId = descriptor ? sourceReferenceTargetId(
        descriptor.block_id, descriptor.item_index
      ) : "";
      if (
        keys !== "alias,block_id,item_index" ||
        !aliasMatch || (!ordinalItem && !exactSplitItem) ||
        !normalizedNonblank(descriptor.block_id) ||
        !nonnegativeInteger(descriptor.item_index) ||
        !block || block.kind !== "list" ||
        (Array.isArray(items) && descriptor.item_index >= items.length) ||
        aliases.has(descriptor.alias) ||
        targetIds.has(targetId)
      ) {
        throw new Error("ALC reader legacy bibliography manifest is invalid");
      }
      blockIds.add(descriptor.block_id);
      targetIds.add(targetId);
      aliases.set(descriptor.alias, targetId);
      itemIndexes.add(descriptor.item_index);
      var blockIndexes = itemIndexesByBlockId.get(descriptor.block_id) || new Set();
      blockIndexes.add(descriptor.item_index);
      itemIndexesByBlockId.set(descriptor.block_id, blockIndexes);
    });
    return {
      blockId: blockIds.size === 1 ? Array.from(blockIds)[0] : "",
      blockIds: blockIds,
      aliases: aliases,
      itemIndexes: itemIndexes,
      itemIndexesByBlockId: itemIndexesByBlockId
    };
  }

  function sourceBibliographyItemIndexes(blockId) {
    return state.sourceBibliographyIndex.itemIndexesByBlockId.get(blockId) ||
      new Set();
  }

  function buildSourceStructuralIndex(descriptors, blocks) {
    var empty = {aliases: new Map(), blockIds: new Set()};
    if (descriptors === undefined) return empty;
    if (!Array.isArray(descriptors) || !Array.isArray(blocks)) {
      throw new Error("ALC reader legacy structural manifest is invalid");
    }
    var blocksById = new Map();
    blocks.forEach(function (block) {
      if (block && normalizedNonblank(block.block_id)) {
        blocksById.set(block.block_id, block);
      }
    });
    var aliases = new Map();
    var blockIds = new Set();
    descriptors.forEach(function (descriptor) {
      var keys = descriptor && typeof descriptor === "object" ?
        Object.keys(descriptor).sort().join(",") : "";
      var block = descriptor ? blocksById.get(descriptor.block_id) : null;
      if (
        keys !== "alias,block_id" ||
        !normalizedNonblank(descriptor.alias) ||
        descriptor.alias.charAt(0) === "#" ||
        !normalizedNonblank(descriptor.block_id) || !block ||
        aliases.has(descriptor.alias)
      ) {
        throw new Error("ALC reader legacy structural manifest is invalid");
      }
      aliases.set(
        descriptor.alias, "block-" + safeToken(descriptor.block_id)
      );
      blockIds.add(descriptor.block_id);
    });
    return {aliases: aliases, blockIds: blockIds};
  }

  function buildSourceNoteIndex(documentValue) {
    var aliases = new Map();
    var targetIds = new Set();
    sourceNotes(documentValue).forEach(function (note) {
      if (
        !note || !normalizedNonblank(note.note_id) ||
        !normalizedNonblank(note.owner_block_id) || aliases.has(note.note_id)
      ) throw new Error("ALC reader source note index is invalid");
      var targetId = "source-note-" + safeToken(note.note_id);
      if (targetIds.has(targetId)) {
        throw new Error("ALC reader source note target is duplicate");
      }
      aliases.set(note.note_id, targetId);
      targetIds.add(targetId);
    });
    return {aliases: aliases, targetIds: targetIds};
  }

  function buildSourceInternalLinkIndex(bibliography, structural, sourceNotes) {
    var aliases = new Map();
    var targetIds = new Set();
    [bibliography, structural, sourceNotes].forEach(function (index) {
      if (!index || !(index.aliases instanceof Map)) {
        throw new Error("ALC reader internal link manifest is invalid");
      }
      index.aliases.forEach(function (targetId, alias) {
        if (
          !normalizedNonblank(alias) || !normalizedNonblank(targetId) ||
          aliases.has(alias)
        ) {
          throw new Error("ALC reader internal link manifest is invalid");
        }
        aliases.set(alias, targetId);
        targetIds.add(targetId);
      });
    });
    return {aliases: aliases, targetIds: targetIds};
  }

  function canonicalReaderTargetId(targetId) {
    return state.sourceInternalLinkIndex.aliases.get(targetId) ||
      state.sourceBibliographyIndex.aliases.get(targetId) || targetId;
  }

  function revealSourceTarget(targetId) {
    if (!state.sourceInternalLinkIndex.targetIds.has(targetId)) return false;
    return revealSourceNavigationTarget();
  }

  function revealSourceReferenceTarget(targetId) {
    if (targetId.indexOf("source-reference-") !== 0) return false;
    var known = Array.from(state.sourceBibliographyIndex.aliases.values())
      .indexOf(targetId) >= 0;
    return known ? revealSourceNavigationTarget() : false;
  }

  function revealSourceNavigationTarget() {
    if (state.sourceVisible) return true;
    state.sourceVisible = true;
    if (state.visibilityReady) {
      renderVisibilityOptions();
      applyVisibility();
    }
    return true;
  }

  function syncSourceBibliographyAlignment(row) {
    var lanes = directChildWithClass(row, "alc-lanes");
    if (!lanes) return false;
    lanes.classList.remove("alc-aligned-bibliography");
    lanes.style.removeProperty("--alc-aligned-list-rows");
    if (
      !row.dataset ||
      row.dataset.blockId !== state.sourceBibliographyIndex.blockId ||
      lanes.children.length !== 2
    ) return false;
    var source = directChildWithClass(lanes, "alc-source-card");
    var translations = Array.from(lanes.children).filter(function (node) {
      return node.classList.contains("alc-fragment") &&
        node.dataset.role === "translation" &&
        !node.classList.contains("is-inline-editing");
    });
    if (!source || translations.length !== 1) return false;
    var sourceLists = directListChildren(source);
    var saved = directChildWithClass(
      translations[0], "alc-fragment-saved-content"
    );
    var markdown = directChildWithClass(saved, "alc-markdown");
    var translatedLists = directListChildren(markdown);
    if (
      sourceLists.length !== 1 || translatedLists.length !== 1 ||
      markdown.children.length !== 1
    ) return false;
    var sourceItems = Array.from(sourceLists[0].children);
    var translatedItems = Array.from(translatedLists[0].children);
    if (
      !sourceItems.length || sourceItems.length !== translatedItems.length ||
      !sourceItems.every(isListItem) || !translatedItems.every(isListItem)
    ) return false;
    lanes.style.setProperty(
      "--alc-aligned-list-rows", String(sourceItems.length)
    );
    lanes.classList.add("alc-aligned-bibliography");
    return true;
  }

  function directChildWithClass(parent, className) {
    return parent && Array.from(parent.children || []).find(function (node) {
      return node.classList && node.classList.contains(className);
    }) || null;
  }

  function directListChildren(parent) {
    return parent ? Array.from(parent.children || []).filter(function (node) {
      return node.tagName === "OL" || node.tagName === "UL";
    }) : [];
  }

  function isListItem(node) {
    return node && node.tagName === "LI";
  }

  function decorateLegacyBibliographyLinks(root) {
    if (!root || typeof root.querySelectorAll !== "function") return;
    Array.from(root.querySelectorAll('a[href^="#bib.bib"]')).filter(
      function (link) {
        return legacyBibliographyTarget(link.getAttribute("href"));
      }
    ).forEach(
      function (link) {
        var sourceHref = link.getAttribute("href") || "";
        var alias = hashTargetId(sourceHref);
        var canonical = state.sourceInternalLinkIndex.aliases.get(alias);
        if (canonical) {
          link.setAttribute("href", "#" + canonical);
          link.removeAttribute("rel");
          return;
        }
        replaceLegacyLinkWithUnavailable(
          link, alias, labels().referenceUnavailable
        );
      }
    );
  }

  function decorateLegacyStructuralLinks(root) {
    if (!root || typeof root.querySelectorAll !== "function") return;
    Array.from(root.querySelectorAll('a[href^="#"]')).filter(
      function (link) {
        var target = link.getAttribute("href");
        return legacyStructuralReference(target) ||
          legacyStructuralTarget(target);
      }
    ).forEach(
      function (link) {
        var sourceHref = link.getAttribute("href") || "";
        var alias = hashTargetId(sourceHref);
        var canonical = state.sourceInternalLinkIndex.aliases.get(alias);
        if (canonical) {
          link.setAttribute("href", "#" + canonical);
          link.removeAttribute("rel");
          return;
        }
        replaceLegacyStructuralLinkWithText(link, alias);
      }
    );
  }

  function replaceLegacyStructuralLinkWithText(link, alias) {
    link.replaceWith(document.createTextNode(link.textContent || alias));
  }

  function replaceLegacyLinkWithUnavailable(link, alias, message) {
    var unavailable = element("span", "alc-unresolved-reference");
    unavailable.textContent = link.textContent || alias;
    unavailable.appendChild(document.createTextNode(" (" + message + ")"));
    unavailable.title = message;
    link.replaceWith(unavailable);
  }

  function decorateScrollableTables(root) {
    if (!root || typeof root.querySelectorAll !== "function") return;
    Array.from(root.querySelectorAll("table")).forEach(function (table) {
      var parent = table.parentElement;
      if (parent && parent.classList.contains("alc-table-scroll")) return;
      var region = element("div", "alc-table-scroll");
      var caption = table.querySelector("caption");
      var labelledBy = table.getAttribute("aria-labelledby") || "";
      if (!caption && labelledBy) caption = document.getElementById(labelledBy);
      region.dataset.tableLabel = String(
        caption && caption.textContent || labels().scrollableTable
      ).replace(/\s+/g, " ").trim();
      region.addEventListener("keydown", function (event) {
        scrollTableWithKeyboard(region, event);
      });
      table.parentNode.insertBefore(region, table);
      region.appendChild(table);
    });
    scheduleScrollableTableSync();
  }

  function scrollTableWithKeyboard(region, event) {
    var maximum = Math.max(
      0, Number(region.scrollWidth) - Number(region.clientWidth)
    );
    if (maximum <= 1) return false;
    var current = Number(region.scrollLeft) || 0;
    var step = Math.max(48, Number(region.clientWidth) * 0.25);
    var next;
    if (event.key === "ArrowLeft") next = current - step;
    else if (event.key === "ArrowRight") next = current + step;
    else if (event.key === "PageUp") next = current - Number(region.clientWidth);
    else if (event.key === "PageDown") next = current + Number(region.clientWidth);
    else if (event.key === "Home") next = 0;
    else if (event.key === "End") next = maximum;
    else return false;
    region.scrollLeft = Math.max(0, Math.min(maximum, next));
    event.preventDefault();
    return true;
  }

  function syncScrollableTableRegion(region) {
    var overflowing = Number(region.scrollWidth) >
      Number(region.clientWidth) + 1;
    region.classList.toggle("is-overflowing", overflowing);
    if (overflowing) {
      region.setAttribute("tabindex", "0");
      region.setAttribute("role", "region");
      region.setAttribute(
        "aria-label", region.dataset.tableLabel || labels().scrollableTable
      );
      return;
    }
    region.removeAttribute("tabindex");
    region.removeAttribute("role");
    region.removeAttribute("aria-label");
  }

  function syncScrollableTables(root) {
    var scope = root && typeof root.querySelectorAll === "function" ?
      root : document;
    Array.from(scope.querySelectorAll(".alc-table-scroll")).forEach(
      syncScrollableTableRegion
    );
  }

  function scheduleScrollableTableSync() {
    if (
      state.tableSyncScheduled ||
      typeof window.requestAnimationFrame !== "function"
    ) return;
    state.tableSyncScheduled = true;
    window.requestAnimationFrame(function () {
      state.tableSyncScheduled = false;
      syncScrollableTables(document);
    });
  }

  function hashTargetId(hash) {
    if (!hash || hash.charAt(0) !== "#") return "";
    try {
      return decodeURIComponent(hash.slice(1));
    } catch (_error) {
      return hash.slice(1);
    }
  }

  function legacyStructuralTarget(target) {
    var alias = hashTargetId(String(target || ""));
    return state.sourceStructuralIndex.aliases.has(alias) ||
      state.sourceNoteIndex.aliases.has(alias);
  }

  function legacyStructuralReference(target) {
    var alias = hashTargetId(String(target || ""));
    return /^S[0-9]+(?:[.][A-Za-z][A-Za-z0-9_-]*)*$/.test(alias);
  }

  function sourceTitle(documentValue) {
    var first = (documentValue.blocks || []).find(function (block) {
      return block.kind === "heading" && block.payload &&
        Number(block.payload.level) === 1;
    });
    return first ? first.payload.text : "";
  }

  function listPathEntries(block) {
    return block && Array.isArray(block.list_path) ? block.list_path : [];
  }

  function listMarkerText(entry, markdown) {
    if (!entry || entry.continuation === true) return "";
    if (entry.ordered === true) {
      return String(Number(entry.item_index) + 1) + ".";
    }
    return markdown ? "-" : "•";
  }

  function listPathMarkers(block) {
    return listPathEntries(block).map(function (entry, depth) {
      return {
        depth: depth,
        text: listMarkerText(entry, false),
        continuation: entry.continuation === true
      };
    });
  }

  function listMarkdownIndent(entry) {
    var marker = entry && entry.ordered === true ?
      String(Number(entry.item_index) + 1) + "." : "-";
    return Math.max(4, marker.length + 1);
  }

  function indentListMarkdown(markdown, width) {
    var padding = " ".repeat(Math.max(0, width));
    return String(markdown || "").split("\n").map(function (line) {
      return line ? padding + line : "";
    }).join("\n");
  }

  function unwrapSoleListItemMarkdown(markdown) {
    var lines = String(markdown || "").split("\n");
    var first = /^(?:[-+*]|[0-9]+[.)])\s+(.+)$/.exec(lines[0] || "");
    if (!first || lines.slice(1).some(function (line) {
      return /^(?:[-+*]|[0-9]+[.)])\s+/.test(line);
    })) return markdown;
    lines[0] = first[1];
    return lines.join("\n");
  }

  function exportListOwnedMarkdown(block, markdown, forceContinuation) {
    var path = listPathEntries(block);
    markdown = String(markdown || "").replace(/\n+$/, "");
    if (!path.length || !markdown) return markdown;
    if (block && block.kind === "list") {
      markdown = unwrapSoleListItemMarkdown(markdown);
    }
    var entry = path[path.length - 1];
    var baseIndent = path.slice(0, -1).reduce(function (total, ancestor) {
      return total + listMarkdownIndent(ancestor);
    }, 0);
    var continuation = forceContinuation === true || entry.continuation === true;
    if (continuation) {
      return indentListMarkdown(
        markdown, baseIndent + listMarkdownIndent(entry)
      );
    }
    var marker = listMarkerText(entry, true);
    var lines = markdown.split("\n");
    var firstPrefix = " ".repeat(baseIndent) + marker + " ";
    var followingIndent = baseIndent + listMarkdownIndent(entry);
    return firstPrefix + lines[0] + (lines.length > 1 ?
      "\n" + indentListMarkdown(lines.slice(1).join("\n"), followingIndent) :
      "");
  }

  function renderListMarkerRail(block) {
    var markers = listPathMarkers(block);
    var rail = element("span", "alc-list-marker-rail");
    rail.style.setProperty("--alc-list-depth", String(markers.length));
    markers.forEach(function (value) {
      var marker = element("span", "alc-list-marker", value.text);
      marker.dataset.listDepth = String(value.depth);
      marker.classList.toggle("is-continuation", value.continuation);
      rail.appendChild(marker);
    });
    return rail;
  }

  function decorateListOwnedCard(card, block, content) {
    var path = listPathEntries(block);
    if (!card || !content || !path.length) return false;
    var item = path[path.length - 1];
    card.classList.add("alc-list-owned-card");
    card.style.setProperty("--alc-list-depth", String(path.length));
    card.dataset.listContainerId = String(item.container_id || "");
    card.dataset.listItemId = String(item.item_id || "");
    card.dataset.listItemIndex = String(item.item_index);
    card.dataset.listSegmentIndex = String(item.segment_index);
    card.dataset.listContinuation = String(item.continuation === true);
    card.insertBefore(renderListMarkerRail(block), content);
    return true;
  }

  function flattenListOwnedFragment(card, block) {
    if (!card || block.kind !== "list" || !listPathEntries(block).length) {
      return;
    }
    var saved = directChildWithClass(card, "alc-fragment-saved-content");
    var markdown = directChildWithClass(saved, "alc-markdown");
    var lists = directListChildren(markdown);
    if (
      !markdown || markdown.children.length !== 1 || lists.length !== 1 ||
      lists[0].children.length !== 1 || !isListItem(lists[0].children[0])
    ) return;
    var list = lists[0];
    var item = list.children[0];
    while (item.firstChild) markdown.insertBefore(item.firstChild, list);
    list.remove();
  }

  function decorateListOwnedFragment(card, block) {
    if (!card || card.dataset.role !== "translation") return;
    flattenListOwnedFragment(card, block);
    decorateListOwnedCard(
      card, block, directChildWithClass(card, "alc-fragment-saved-content")
    );
  }

  function isPdfPageMarkerBlock(block) {
    if (!block || block.kind !== "paragraph") return false;
    var text = String((block.payload || {}).text || "");
    return /^<!-- PDF_PAGE: [1-9][0-9]* -->$/.test(text);
  }

  function isStandaloneHtmlCommentBlock(block) {
    if (!block || block.kind !== "paragraph") return false;
    var payload = block.payload || {};
    if (Array.isArray(payload.inline_spans) && payload.inline_spans.length) {
      return false;
    }
    return /^\s*<!--[\s\S]*?-->\s*$/.test(String(payload.text || ""));
  }

  function groupedFragments(documentValue) {
    var groups = new Map();
    state.selected.forEach(function (fragment) {
      if (!fragmentIsVisible(fragment)) return;
      if (sourceNoteTranslationId(documentValue, fragment)) return;
      var target = fragmentTargetId(fragment);
      if (!target) return;
      var values = groups.get(target) || [];
      values.push(fragment);
      groups.set(target, values);
    });
    groups.forEach(function (values) {
      values.sort(function (left, right) {
        return left.priority - right.priority ||
          left.fragment_id.localeCompare(right.fragment_id);
      });
    });
    return groups;
  }

  function fragmentIsVisible(fragment) {
    if (!fragment || fragment.deleted === true) return false;
    return !(
      fragment.role === "note" &&
      !String(fragment.title || "").trim() &&
      !normalizeMarkdown(fragment.markdown_body).trim()
    );
  }

  function fragmentTargetId(fragment) {
    var anchor = fragment && fragment.anchor;
    var target = anchor && anchor.target_id;
    if (anchor && anchor.kind === "section") {
      target = ensureSourceIndexes().sectionAnchors.get(target) || null;
    }
    return target || null;
  }

  function renderSourceFrontMatter(entry) {
    var root = element("section", "alc-source-front-matter");
    root.dataset.frontMatterId = String(entry.front_matter_id || "");
    var heading = element("h2", "alc-visually-hidden", labels().authors);
    heading.id = "source-front-matter-" + safeToken(entry.front_matter_id) + "-heading";
    root.setAttribute("aria-labelledby", heading.id);
    root.appendChild(heading);

    var affiliationsByMarker = new Map();
    var affiliationsById = new Map();
    (entry.affiliations || []).forEach(function (affiliation) {
      var marker = String(affiliation.marker || "");
      var affiliationId = String(affiliation.affiliation_id || "");
      if (
        (marker && affiliationsByMarker.has(marker)) ||
        !affiliationId || affiliationsById.has(affiliationId)
      ) {
        throw new Error("source front matter affiliation markers are invalid");
      }
      if (marker) affiliationsByMarker.set(marker, affiliation);
      affiliationsById.set(affiliationId, affiliation);
    });

    var authorsById = new Map();
    (entry.authors || []).forEach(function (author) {
      var authorId = String(author.author_id || "");
      if (!authorId || authorsById.has(authorId)) {
        throw new Error("source front matter author identities are invalid");
      }
      authorsById.set(authorId, author);
      (author.markers || []).forEach(function (marker) {
        if (!affiliationsByMarker.has(String(marker))) {
          throw new Error("source front matter author marker is unresolved");
        }
      });
    });

    if (entry.creator_flow !== undefined) {
      root.appendChild(renderSourceCreatorFlow(
        entry, authorsById, affiliationsById
      ));
      return root;
    }

    var authors = element("ul", "alc-source-author-list");
    (entry.authors || []).forEach(function (author) {
      var item = element("li", "alc-source-author");
      item.appendChild(renderSourceAuthorIdentity(author));

      var contacts = element("div", "alc-source-author-contacts");
      (author.contacts || []).forEach(function (contact) {
        contacts.appendChild(renderSourceAuthorContact(contact));
      });
      if (contacts.childNodes.length) item.appendChild(contacts);
      authors.appendChild(item);
    });
    root.appendChild(authors);
    if ((entry.affiliations || []).length) {
      var affiliationsHeading = element(
        "h3", "alc-visually-hidden", labels().affiliations
      );
      affiliationsHeading.id =
        "source-front-matter-" + safeToken(entry.front_matter_id) +
        "-affiliations";
      root.appendChild(affiliationsHeading);
      var affiliations = element("ul", "alc-source-affiliations");
      affiliations.setAttribute("aria-labelledby", affiliationsHeading.id);
      (entry.affiliations || []).forEach(function (affiliation) {
        var affiliationItem = element("li", "alc-source-affiliation-item");
        affiliationItem.appendChild(element(
          "sup", "alc-source-affiliation-marker", affiliation.marker || ""
        ));
        affiliationItem.appendChild(element(
          "span", "alc-source-affiliation", affiliation.text || ""
        ));
        affiliations.appendChild(affiliationItem);
      });
      root.appendChild(affiliations);
    }
    return root;
  }

  function renderSourceAuthorIdentity(author) {
    var identity = element("div", "alc-source-author-identity");
    identity.appendChild(element(
      "span", "alc-source-author-name", author.name || ""
    ));
    (author.markers || []).forEach(function (marker) {
      identity.appendChild(element("sup", "alc-source-author-marker", marker));
    });
    if (author.orcid_url) {
      var orcid = element("a", "alc-source-author-orcid", labels().orcid);
      orcid.href = author.orcid_url;
      orcid.rel = "noopener noreferrer";
      orcid.setAttribute(
        "aria-label", labels().orcid + " · " + String(author.name || "")
      );
      identity.appendChild(orcid);
    }
    return identity;
  }

  function renderSourceAuthorContact(contact) {
    if (contact.target) {
      var link = element("a", "alc-source-author-contact", contact.value || "");
      link.href = contact.target;
      link.rel = "noopener noreferrer";
      if (contact.label) link.title = contact.label;
      return link;
    }
    return element("span", "alc-source-author-contact", contact.value || "");
  }

  function renderSourceAffiliationOccurrence(affiliation) {
    var value = element("div", "alc-source-creator-slot-affiliation");
    value.appendChild(element(
      "sup", "alc-source-affiliation-marker", affiliation.marker || ""
    ));
    value.appendChild(element(
      "span", "alc-source-affiliation", affiliation.text || ""
    ));
    return value;
  }

  function renderSourceCreatorFlow(entry, authorsById, affiliationsById) {
    var flow = entry.creator_flow;
    if (
      !plainObject(flow) || !Array.isArray(flow.creators) ||
      !Number.isInteger(flow.creator_count) ||
      flow.creator_count !== flow.creators.length ||
      !Number.isInteger(flow.slot_count)
    ) throw new Error("source front matter creator flow is invalid");
    var creators = element("ol", "alc-source-creator-flow");
    var slotCount = 0;
    flow.creators.forEach(function (creator, creatorIndex) {
      if (
        !plainObject(creator) || creator.ordinal !== creatorIndex ||
        !normalizedNonblank(creator.creator_id) ||
        !normalizedNonblank(creator.author_id) ||
        !Array.isArray(creator.slots)
      ) throw new Error("source front matter creator is invalid");
      var author = authorsById.get(creator.author_id);
      if (!author) throw new Error("source front matter creator author is unknown");
      var item = element("li", "alc-source-creator");
      item.dataset.creatorId = creator.creator_id;
      var authorSlots = 0;
      creator.slots.forEach(function (slot, slotIndex) {
        slotCount += 1;
        if (
          !plainObject(slot) || slot.ordinal !== slotIndex ||
          !normalizedNonblank(slot.slot_id)
        ) throw new Error("source front matter creator slot is invalid");
        if (slot.kind === "author") {
          authorSlots += 1;
          item.appendChild(renderSourceAuthorIdentity(author));
        } else if (slot.kind === "contact") {
          if (
            !Number.isInteger(slot.contact_index) ||
            !author.contacts || !author.contacts[slot.contact_index]
          ) throw new Error("source front matter contact slot is invalid");
          var contact = element("div", "alc-source-author-contacts");
          contact.appendChild(renderSourceAuthorContact(
            author.contacts[slot.contact_index]
          ));
          item.appendChild(contact);
        } else if (slot.kind === "affiliation") {
          var affiliation = affiliationsById.get(slot.affiliation_id);
          if (!affiliation) {
            throw new Error("source front matter affiliation slot is invalid");
          }
          item.appendChild(renderSourceAffiliationOccurrence(affiliation));
        } else {
          throw new Error("source front matter creator slot kind is unknown");
        }
      });
      if (authorSlots !== 1) {
        throw new Error("source front matter creator author slot is invalid");
      }
      creators.appendChild(item);
    });
    if (slotCount !== flow.slot_count) {
      throw new Error("source front matter creator slot count differs");
    }
    return creators;
  }

  function regularTranslationFragments(blockId) {
    return (state.fragmentGroups.get(blockId) || []).filter(function (item) {
      return item.priority <= 100 && item.role === "translation" &&
        item.fragment_id !== state.primaryTitleFragmentId;
    });
  }

  function translationSourceNoteToken(noteId) {
    return "[^" + String(noteId || "") + "]";
  }

  function decorateTranslationSourceNoteTokens(rendered, fragment) {
    var documentValue = state.payload.publication.source_document;
    if (
      !rendered || !fragment || fragment.role !== "translation" ||
      sourceNoteTranslationId(documentValue, fragment)
    ) return;
    var blockId = fragmentTargetId(fragment);
    var notes = sourceNotesForBlock(documentValue, blockId);
    if (!notes.length) return;
    notes.forEach(function (note) {
      var token = translationSourceNoteToken(note.note_id);
      var matches = [];
      var walker = document.createTreeWalker(
        rendered, window.NodeFilter.SHOW_TEXT
      );
      var node;
      while ((node = walker.nextNode())) {
        var parent = node.parentElement;
        if (parent && parent.closest("a,code,pre,.math,.katex")) continue;
        var index = String(node.data || "").indexOf(token);
        while (index >= 0) {
          matches.push({node: node, index: index});
          index = String(node.data || "").indexOf(token, index + token.length);
        }
      }
      if (matches.length > 1) {
        throw new Error("translation source note token is duplicate");
      }
      if (!matches.length) return;
      var match = matches[0];
      var tokenNode = match.node.splitText(match.index);
      tokenNode.splitText(token.length);
      tokenNode.replaceWith(renderTranslationSourceNoteReference(note));
    });
  }

  function translatedSourceNoteBacklinkTarget(note, ownerRow) {
    var translatedTarget = "translation-note-ref-" + safeToken(note.note_id);
    if (
      ownerRow && ownerRow.querySelector &&
      ownerRow.querySelector("#" + translatedTarget)
    ) return "#" + translatedTarget;
    return "#source-note-ref-" + safeToken(note.note_id);
  }

  function renderSourceNoteGroup(block, ownerRow) {
    var documentValue = state.payload.publication.source_document;
    var notes = sourceNotesForBlock(documentValue, block.block_id);
    if (!notes.length) return null;
    var translations = sourceNoteTranslations(documentValue);
    var group = element("div", "alc-source-notes");
    notes.forEach(function (note) {
      var row = element("aside", "alc-source-note-row");
      row.id = "source-note-" + safeToken(note.note_id);
      row.dataset.sourceNoteId = note.note_id;
      row.setAttribute("role", "note");
      var lanes = element("div", "alc-source-note-lanes");
      var source = element("section", "alc-source-note-card");
      source.lang = (state.payload.publication.reader_profile || {}).source_language ||
        document.documentElement.lang;
      var sourceBody = element("p");
      var back = element("a", "alc-source-note-backref", String(note.marker || ""));
      back.href = "#source-note-ref-" + safeToken(note.note_id);
      back.setAttribute("aria-label", labels().sourceNoteBack);
      sourceBody.appendChild(back);
      sourceBody.appendChild(document.createTextNode(" "));
      var content = element("span", "alc-source-note-content");
      appendInlineSpans(content, note.inline_spans, note.body);
      sourceBody.appendChild(content);
      source.appendChild(sourceBody);
      lanes.appendChild(source);

      var translation = translations.get(note.note_id);
      if (translation) {
        row.classList.add("has-translation");
        var translated = renderFragment(translation);
        translated.classList.add(
          "alc-source-note-card", "alc-source-note-translation"
        );
        var translatedContent = translated.querySelector(
          ".alc-fragment-saved-content"
        );
        translatedContent.classList.add("alc-source-note-translation-content");
        var translatedBack = element(
          "a", "alc-source-note-backref alc-translation-note-backref",
          String(note.marker || "")
        );
        translatedBack.href = translatedSourceNoteBacklinkTarget(note, ownerRow);
        translatedBack.setAttribute("aria-label", labels().sourceNoteBack);
        translatedContent.insertBefore(
          translatedBack, translatedContent.firstChild
        );
        lanes.appendChild(translated);
      }
      row.appendChild(lanes);
      group.appendChild(row);
    });
    return group;
  }

  function sourceClassificationBlocks(documentValue, relation) {
    var ids = [relation.heading_block_id].concat(relation.value_block_ids);
    var byId = new Map((documentValue.blocks || []).map(function (block) {
      return [block.block_id, block];
    }));
    return ids.map(function (blockId) {
      var block = byId.get(blockId);
      if (!block) throw new Error("source classification block is missing");
      return block;
    });
  }

  function renderSourceClassificationRow(relation) {
    var documentValue = state.payload.publication.source_document;
    var blocks = sourceClassificationBlocks(documentValue, relation);
    var headingBlock = blocks[0];
    var row = element(
      "article", "alc-source-row alc-source-classification-row"
    );
    row.id = "block-" + safeToken(headingBlock.block_id);
    row.dataset.blockId = headingBlock.block_id;
    row.dataset.blockKind = headingBlock.kind;
    row.dataset.sourceRoles = "classification";
    row.dataset.sourceClassificationId = relation.classification_id;
    row.dataset.sourceHeadingLevel = String(
      effectiveReaderHeadingLevel(
        headingBlock, sourcePresentationBlock(documentValue, headingBlock.block_id)
      )
    );
    row.classList.add("alc-source-role-classification");

    var lanes = element("div", "alc-lanes alc-source-classification-lanes");
    var source = element("section", "alc-source-card");
    source.dataset.role = "source";
    source.lang = (state.payload.publication.reader_profile || {}).source_language ||
      document.documentElement.lang;
    source.appendChild(renderSourceBlock(headingBlock));
    source.appendChild(renderCardActions("source", headingBlock.block_id, null));
    setupTouchCardActions(source);
    lanes.appendChild(source);

    var target = element("div", "alc-source-classification-target");
    var editorContext = classificationValueEditorContext();
    if (
      editorContext &&
      editorContext.relation.classification_id === relation.classification_id
    ) target.classList.add("is-editing-classification-value");
    var renderedHeadingTranslation = false;
    var renderedValueTranslation = false;
    var classificationFragments = [];
    var valueFragments = [];
    blocks.forEach(function (block, blockIndex) {
      var fragments = regularTranslationFragments(block.block_id);
      if (
        blockIndex > 0 && renderedHeadingTranslation &&
        !renderedValueTranslation && fragments.length
      ) {
        target.appendChild(element(
          "span", "alc-source-classification-separator", relation.separator
        ));
      }
      fragments.forEach(function (fragment, fragmentIndex) {
        classificationFragments.push(fragment);
        if (blockIndex > 0) valueFragments.push(fragment);
        var card = renderFragment(fragment);
        card.classList.add("alc-source-classification-fragment");
        card.classList.toggle(
          "alc-source-classification-heading-fragment", blockIndex === 0
        );
        if (block.kind === "figure") mirrorSourceFigure(source, card, block);
        if (block.kind === "table") mirrorSourceTable(source, card, block);
        decorateListOwnedFragment(card, block);
        target.appendChild(card);
      });
      if (blockIndex === 0 && fragments.length) {
        renderedHeadingTranslation = true;
      } else if (blockIndex > 0 && fragments.length) {
        renderedValueTranslation = true;
      }
    });
    if (renderedHeadingTranslation && renderedValueTranslation) {
      target.appendChild(renderClassificationActions(
        relation,
        classificationFragments,
        valueFragments.length === 1 ? valueFragments[0] : null
      ));
      setupTouchCardActions(target);
    }
    if (target.childNodes.length) {
      lanes.classList.add("has-parallel-translation");
      lanes.appendChild(target);
    }
    row.appendChild(lanes);

    blocks.forEach(function (block) {
      var notes = renderSourceNoteGroup(block, row);
      if (notes) {
        row.classList.add("alc-has-source-notes");
        row.appendChild(notes);
      }
    });
    var full = blocks.flatMap(function (block) {
      return (state.fragmentGroups.get(block.block_id) || []).filter(function (item) {
        return item.priority >= 101 ||
          (item.priority <= 100 && item.role !== "translation");
      });
    });
    if (full.length) {
      var fullRows = element("div", "alc-full-rows");
      full.forEach(function (item) {
        fullRows.appendChild(renderFragment(item));
      });
      row.appendChild(fullRows);
    }
    var noteButton = iconButton(
      "alc-note-button alc-icon-button", "+", labels().addNote
    );
    noteButton.addEventListener("click", function () {
      openNewEditor(headingBlock);
    });
    row.appendChild(noteButton);
    return row;
  }

  function renderSourceRow(block, fragments) {
    var row = element("article", "alc-source-row");
    row.id = "block-" + safeToken(block.block_id);
    row.dataset.blockId = block.block_id;
    row.dataset.blockKind = block.kind;
    var presentation = ["heading", "paragraph", "list", "figure", "table"]
      .indexOf(block.kind) >= 0 ? sourcePresentationBlock(
        state.payload.publication.source_document, block.block_id
      ) : null;
    if (presentation && presentation.roles.length) {
      row.dataset.sourceRoles = presentation.roles.join(" ");
      presentation.roles.forEach(function (role) {
        row.classList.add("alc-source-role-" + safeToken(role));
      });
    }
    if (block.kind === "heading") {
      row.dataset.sourceHeadingLevel = String(
        effectiveReaderHeadingLevel(block, presentation)
      );
    }
    if (sourceBibliographyItemIndexes(block.block_id).size) {
      row.classList.add("alc-source-bibliography-row");
    }
    if (state.sourceStructuralIndex.blockIds.has(block.block_id)) {
      row.classList.add("alc-source-navigation-target");
      row.tabIndex = -1;
    }
    if (
      block.block_id === state.primaryTitleBlockId &&
      state.primaryTitleFragmentId
    ) {
      row.classList.add("alc-promoted-title-row");
    }
    var lanes = element("div", "alc-lanes");
    lanes.classList.toggle(
      "has-parallel-translation",
      fragments.some(function (item) {
        return item.priority <= 100 && item.role === "translation" &&
          item.fragment_id !== state.primaryTitleFragmentId;
      })
    );
    var source = element("section", "alc-source-card");
    source.dataset.role = "source";
    source.lang = (state.payload.publication.reader_profile || {}).source_language ||
      document.documentElement.lang;
    var sourceBlock = renderSourceBlock(block);
    if (listPathEntries(block).length) {
      var sourceContent = element("div", "alc-list-owned-content");
      sourceContent.appendChild(sourceBlock);
      source.appendChild(sourceContent);
      decorateListOwnedCard(source, block, sourceContent);
      var deepestOwner = listPathEntries(block).slice(-1)[0];
      row.dataset.listItemId = String(deepestOwner.item_id || "");
      row.dataset.listSegmentIndex = String(deepestOwner.segment_index);
      row.dataset.listContinuation = String(
        deepestOwner.continuation === true
      );
    } else {
      source.appendChild(sourceBlock);
    }
    source.appendChild(renderCardActions("source", block.block_id, null));
    setupTouchCardActions(source);
    lanes.appendChild(source);

    fragments.filter(function (item) {
      return item.priority <= 100 &&
        item.fragment_id !== state.primaryTitleFragmentId;
    }).forEach(function (item) {
      var card = renderFragment(item);
      if (block.kind === "figure" && item.role === "translation") {
        mirrorSourceFigure(source, card, block);
      }
      if (block.kind === "table" && item.role === "translation") {
        mirrorSourceTable(source, card, block);
      }
      decorateListOwnedFragment(card, block);
      lanes.appendChild(card);
    });
    row.appendChild(lanes);
    if (block.kind === "table") {
      syncParallelTableCaptionAlignment(lanes, block);
    }

    var sourceNoteGroup = renderSourceNoteGroup(block, row);
    if (sourceNoteGroup) {
      row.classList.add("alc-has-source-notes");
      row.appendChild(sourceNoteGroup);
    }

    var full = fragments.filter(function (item) {
      return item.priority >= 101;
    });
    if (full.length) {
      var fullRows = element("div", "alc-full-rows");
      full.forEach(function (item) { fullRows.appendChild(renderFragment(item)); });
      row.appendChild(fullRows);
    }
    markDeliveryState(row, block.block_id);
    var noteButton = iconButton(
      "alc-note-button alc-icon-button", "+", labels().addNote
    );
    noteButton.addEventListener("click", function () {
      openNewEditor(block);
    });
    row.appendChild(noteButton);
    syncSourceBibliographyAlignment(row);
    return row;
  }

  function mirrorSourceFigure(source, card, block) {
    var sourceFigure = source && source.querySelector("figure");
    var saved = card && card.querySelector(".alc-fragment-saved-content");
    if (!sourceFigure || !saved || saved.querySelector("img")) return;
    var figure = sourceFigure.cloneNode(true);
    figure.classList.add("alc-translation-figure");
    if (figure.id) figure.removeAttribute("id");
    Array.prototype.forEach.call(figure.querySelectorAll("[id]"), function (node) {
      node.removeAttribute("id");
    });
    var caption = figure.querySelector("figcaption");
    if (caption) caption.remove();
    var markdown = saved.querySelector(".alc-markdown");
    var figureCaptionText = (block.payload || {}).caption;
    var captionPresentation = typeof figureCaptionText === "string" &&
      Boolean(figureCaptionText.trim()) ?
      sourceCaptionPresentation(
        state.payload.publication.source_document, block.block_id
      ) : null;
    if (markdown && captionPresentation) {
      markdown.classList.add("alc-figure-caption");
      applySourceCaptionPresentation(
        markdown, captionPresentation
      );
    }
    if (
      captionPresentation &&
      captionPresentation.placement === "before_content"
    ) {
      saved.insertAdjacentElement("afterend", figure);
    } else {
      saved.insertAdjacentElement("beforebegin", figure);
    }
    card.classList.add("alc-translation-figure-card");
  }

  function retargetMirroredSourceNoteReferences(table, block) {
    var documentValue = state.payload.publication.source_document;
    sourceNotesForBlock(documentValue, block.block_id).forEach(function (note) {
      var anchor = note.anchor || {};
      if (
        anchor.field !== "table_header" && anchor.field !== "table_cell"
      ) return;
      var selector =
        '[data-source-field="' + anchor.field + '"]' +
        '[data-source-column-index="' + anchor.column_index + '"]';
      if (anchor.field === "table_cell") {
        selector += '[data-source-row-index="' + anchor.row_index + '"]';
      }
      var cell = table.querySelector(selector);
      var references = cell ? Array.from(
        cell.querySelectorAll(".alc-source-note-ref")
      ).filter(function (reference) {
        return reference.textContent === String(note.marker || "");
      }) : [];
      if (references.length !== 1) {
        throw new Error("mirrored Table source note anchor is invalid");
      }
      var reference = references[0];
      reference.id = "translation-note-ref-" + safeToken(note.note_id);
      reference.classList.add("alc-translation-note-ref");
      var link = reference.querySelector("a");
      if (!link) throw new Error("mirrored Table source note link is missing");
      link.href = "#source-note-" + safeToken(note.note_id);
      link.setAttribute(
        "aria-label", labels().sourceNote + " " + String(note.marker || "")
      );
    });
  }

  function mirrorSourceTable(source, card, block) {
    var sourceFigure = source && source.querySelector(".alc-table-figure");
    var sourceTable = sourceFigure && sourceFigure.querySelector(":scope > table");
    var saved = card && card.querySelector(".alc-fragment-saved-content");
    var markdown = saved && saved.querySelector(".alc-markdown");
    var translatedTable = markdown && markdown.querySelector("table");
    if (!sourceTable || !markdown) return;
    var tableRoot = translatedTable && translatedTable.parentElement &&
      translatedTable.parentElement.classList.contains("alc-table-scroll") ?
      translatedTable.parentElement : translatedTable;
    var table = sourceTable.cloneNode(true);
    table.removeAttribute("aria-labelledby");
    Array.from(table.querySelectorAll("[id]")).forEach(function (node) {
      node.removeAttribute("id");
    });
    retargetMirroredSourceNoteReferences(table, block);
    if (translatedTable) {
      translatedTable.replaceWith(table);
    } else {
      var placement = sourceCaptionPresentation(
        state.payload.publication.source_document, block.block_id
      );
      if (placement && placement.placement === "after_content") {
        markdown.insertBefore(table, markdown.firstChild);
      } else {
        markdown.appendChild(table);
      }
      tableRoot = table;
    }
    var directChildren = Array.from(markdown.children);
    var captionCandidates = directChildren.filter(function (node) {
      return node !== tableRoot && node.tagName === "P";
    });
    var tableCaptionText = (block.payload || {}).caption;
    var captionPresentation = typeof tableCaptionText === "string" &&
      Boolean(tableCaptionText.trim()) ?
      sourceCaptionPresentation(
        state.payload.publication.source_document, block.block_id
      ) : null;
    var sourceCaptionAfter = captionPresentation &&
      captionPresentation.placement === "after_content";
    if (
      captionCandidates.length === 1 &&
      directChildren.every(function (node) {
        return node === tableRoot || node === captionCandidates[0];
      })
    ) {
      captionCandidates[0].classList.add("alc-table-caption");
      applySourceCaptionPresentation(captionCandidates[0], captionPresentation);
      if (captionPresentation && captionPresentation.placement === "embedded") {
        var embeddedCaption = table.querySelector(":scope > caption");
        if (!embeddedCaption) {
          throw new Error("embedded source Table caption is missing");
        }
        embeddedCaption.replaceChildren(
          ...Array.from(captionCandidates[0].childNodes)
        );
        embeddedCaption.classList.add("alc-table-caption");
        applySourceCaptionPresentation(
          embeddedCaption, captionPresentation
        );
        captionCandidates[0].remove();
      } else if (sourceCaptionAfter) {
        markdown.appendChild(captionCandidates[0]);
      } else {
        markdown.insertBefore(captionCandidates[0], tableRoot);
      }
    }
    if (captionPresentation) {
      card.dataset.tableCaptionPlacement = captionPresentation.placement;
    }
    decorateScrollableTables(markdown);
    syncScrollableTables(markdown);
    card.classList.add("alc-translation-table-card");
  }

  function tableCaptionPrecedesContent(caption) {
    var next = caption && caption.nextElementSibling;
    if (!next) return false;
    if (next.tagName === "TABLE") return true;
    return Boolean(
      next.classList && next.classList.contains("alc-table-scroll") &&
      next.querySelector && next.querySelector(":scope > table")
    );
  }

  function syncParallelTableCaptionAlignment(lanes, block) {
    var tableCaptionText = (block.payload || {}).caption;
    if (typeof tableCaptionText !== "string" || !tableCaptionText.trim()) {
      return;
    }
    var presentation = sourceCaptionPresentation(
      state.payload.publication.source_document, block.block_id
    );
    var captions = Array.from(lanes.querySelectorAll(
      ":scope > .alc-source-card .alc-table-caption, " +
      ":scope > .alc-fragment[data-role=\"translation\"] .alc-table-caption"
    ));
    if (captions.length < 2) return;
    if (presentation) {
      if (presentation.placement !== "before_content") return;
    } else if (!captions.every(tableCaptionPrecedesContent)) {
      return;
    }
    lanes.classList.add("alc-parallel-table-caption-before");
    var width = null;
    var frame = null;
    function align() {
      frame = null;
      var nextWidth = lanes.getBoundingClientRect().width;
      if (!nextWidth) return;
      var widthChanged = width === null || Math.abs(nextWidth - width) >= 0.5;
      var renderedHeight = Math.max.apply(null, captions.map(function (caption) {
        return caption.getBoundingClientRect().height;
      }));
      if (!widthChanged) {
        var appliedHeight = Number.parseFloat(lanes.style.getPropertyValue(
          "--alc-parallel-table-caption-height"
        ));
        if (renderedHeight > appliedHeight + 0.5) {
          lanes.style.setProperty(
            "--alc-parallel-table-caption-height", renderedHeight + "px"
          );
        }
        return;
      }
      width = nextWidth;
      lanes.style.removeProperty("--alc-parallel-table-caption-height");
      var height = Math.max.apply(null, captions.map(function (caption) {
        return caption.getBoundingClientRect().height;
      }));
      if (height > 0) {
        lanes.style.setProperty(
          "--alc-parallel-table-caption-height", height + "px"
        );
      }
    }
    function scheduleAlignment() {
      if (frame !== null) return;
      frame = window.requestAnimationFrame(align);
    }
    scheduleAlignment();
    if (typeof ResizeObserver === "function") {
      var observer = new ResizeObserver(scheduleAlignment);
      observer.observe(lanes);
      lanes._alcTableCaptionResizeObserver = observer;
    }
  }

  function sourceFigureTargetPanels(documentValue) {
    var manifest = ((documentValue || {}).metadata || {})
      .source_target_manifest;
    if (manifest === undefined) return new Map();
    if (
      !plainObject(manifest) ||
      manifest.schema_version !== "ac.document.source_target_manifest.v1" ||
      !Array.isArray(manifest.targets)
    ) throw new Error("source Figure target manifest is invalid");
    var output = new Map();
    manifest.targets.forEach(function (target) {
      if (!target || target.kind !== "figure" ||
        !Array.isArray(target.panels) || !target.panels.length) return;
      if (!normalizedNonblank(target.block_id) || output.has(target.block_id)) {
        throw new Error("source Figure panel targets reuse a block");
      }
      output.set(target.block_id, target.panels);
    });
    return output;
  }

  function positiveFigureDimension(value) {
    return Number.isInteger(value) && !Number.isNaN(value) &&
      value >= 1 && value <= 1000000;
  }

  function figureIntegerGcd(left, right) {
    var a = Math.abs(left);
    var b = Math.abs(right);
    while (b) {
      var remainder = a % b;
      a = b;
      b = remainder;
    }
    return a;
  }

  function validateSourceFigurePanelDimensions(panel, neutral) {
    var width = panel.display_width;
    var height = panel.display_height;
    var dimensionSource = panel.dimension_source;
    var dimensionsAbsent = width === null && height === null;
    if (dimensionsAbsent) {
      if (dimensionSource !== null) {
        throw new Error("source Figure panel dimension provenance is invalid");
      }
    } else if (
      !positiveFigureDimension(width) || !positiveFigureDimension(height) ||
      dimensionSource !== "attributes:width,height"
    ) {
      throw new Error("source Figure panel dimensions are invalid");
    }
    var ratio = panel.aspect_ratio;
    var ratioSource = panel.aspect_ratio_source;
    if (ratio === null) {
      if (ratioSource !== null) {
        throw new Error("source Figure aspect provenance is invalid");
      }
    } else if (
      !Array.isArray(ratio) || ratio.length !== 2 ||
      !positiveFigureDimension(ratio[0]) ||
      !positiveFigureDimension(ratio[1]) ||
      figureIntegerGcd(ratio[0], ratio[1]) !== 1 ||
      ratioSource !== "style:aspect-ratio"
    ) {
      throw new Error("source Figure aspect ratio is invalid");
    }
    if (width !== null && ratio !== null) {
      var divisor = figureIntegerGcd(width, height);
      if (width / divisor !== ratio[0] || height / divisor !== ratio[1]) {
        throw new Error("source Figure aspect ratio differs from dimensions");
      }
    }
    if (neutral && (!dimensionsAbsent || ratio !== null)) {
      throw new Error("neutral source Figure claims display geometry");
    }
  }

  function validateSourceFigureLayout(entry, targetPanels) {
    var layout = entry.layout;
    var panels = entry.panels;
    if (
      !plainObject(layout) || Object.keys(layout).sort().join(",") !==
        "break_after_panel_indexes,break_source,column_count,column_source," +
        "kind,row_count,row_sources,rows" ||
      !Array.isArray(panels) || !panels.length ||
      !Array.isArray(targetPanels) || panels.length !== targetPanels.length ||
      ["single", "flex", "neutral"].indexOf(layout.kind) < 0 ||
      !Array.isArray(layout.rows) ||
      !Array.isArray(layout.row_sources) ||
      !Array.isArray(layout.break_after_panel_indexes)
    ) throw new Error("source Figure layout is invalid");
    var neutral = layout.kind === "neutral";
    var expectedPositions = new Map();
    if (neutral) {
      if (
        layout.column_count !== null || layout.row_count !== null ||
        layout.rows.length || layout.column_source !== null ||
        layout.row_sources.length ||
        layout.break_after_panel_indexes.length || layout.break_source !== null
      ) throw new Error("neutral source Figure claims authored layout");
    } else {
      var sourceContracts = {
        "latexml_ar5iv_direct_graphic": ["single", 1],
        "class:ltx_flex_size_1": ["flex", 1],
        "class:ltx_flex_size_2": ["flex", 2],
        "class:ltx_flex_size_3": ["flex", 3]
      };
      if (
        !Number.isInteger(layout.column_count) || layout.column_count < 1 ||
        !Number.isInteger(layout.row_count) || layout.row_count < 1 ||
        layout.row_count !== layout.rows.length ||
        layout.row_count !== layout.row_sources.length
      ) throw new Error("source Figure layout provenance is invalid");
      var flattened = [];
      var rowEnds = new Set();
      var rowCapacities = [];
      var normalizedRowSources = [];
      layout.rows.forEach(function (row, rowIndex) {
        var rowSource = layout.row_sources[rowIndex];
        var rowContract = sourceContracts[rowSource];
        if (
          !rowContract || rowContract[0] !== layout.kind ||
          !Array.isArray(row) || !row.length || row.length > rowContract[1]
        ) {
          throw new Error("source Figure layout row is invalid");
        }
        normalizedRowSources.push(rowSource);
        rowCapacities.push(rowContract[1]);
        row.forEach(function (panelIndex, columnIndex) {
          if (!Number.isInteger(panelIndex) || panelIndex < 0) {
            throw new Error("source Figure layout row index is invalid");
          }
          flattened.push(panelIndex);
          expectedPositions.set(panelIndex, [rowIndex, columnIndex]);
        });
        if (rowIndex < layout.rows.length - 1) rowEnds.add(row[row.length - 1]);
      });
      if (layout.column_count !== Math.max.apply(null, rowCapacities)) {
        throw new Error("source Figure layout column count is invalid");
      }
      var uniqueRowSources = new Set(normalizedRowSources);
      var expectedColumnSource = uniqueRowSources.size === 1 ?
        normalizedRowSources[0] : null;
      if (layout.column_source !== expectedColumnSource) {
        throw new Error("source Figure layout column provenance is invalid");
      }
      if (flattened.some(function (panelIndex, index) {
        return panelIndex !== index;
      }) || flattened.length !== panels.length) {
        throw new Error("source Figure layout does not preserve panel order");
      }
      var previousBreak = -1;
      layout.break_after_panel_indexes.forEach(function (panelIndex) {
        if (
          !Number.isInteger(panelIndex) || panelIndex <= previousBreak ||
          panelIndex >= panels.length - 1 || !rowEnds.has(panelIndex)
        ) throw new Error("source Figure layout break is invalid");
        previousBreak = panelIndex;
      });
      if (
        layout.break_after_panel_indexes.length ?
          layout.break_source !== "class:ltx_flex_break" :
          layout.break_source !== null
      ) throw new Error("source Figure break provenance is invalid");
      if (layout.kind === "single" && (
        panels.length !== 1 || stableStringify(layout.rows) !== "[[0]]" ||
        layout.break_after_panel_indexes.length
      )) throw new Error("single source Figure layout is invalid");
    }
    var occupied = new Set();
    panels.forEach(function (panel, index) {
      var target = targetPanels[index];
      if (
        !plainObject(panel) || Object.keys(panel).sort().join(",") !==
          "aspect_ratio,aspect_ratio_source,column_index,dimension_source," +
          "display_height,display_width,panel_index,row_index,source_id" ||
        !target || panel.panel_index !== index || target.panel_index !== index ||
        !normalizedNonblank(panel.source_id) ||
        panel.source_id !== target.source_id
      ) throw new Error("source Figure panel binding is invalid");
      if (neutral) {
        if (panel.row_index !== null || panel.column_index !== null) {
          throw new Error("neutral source Figure panel claims a position");
        }
      } else {
        var position = expectedPositions.get(index);
        var identity = String(panel.row_index) + ":" + panel.column_index;
        if (
          !position || panel.row_index !== position[0] ||
          panel.column_index !== position[1] ||
          panel.row_index >= layout.row_count ||
          panel.column_index >= layout.column_count || occupied.has(identity)
        ) throw new Error("source Figure panel position is invalid");
        occupied.add(identity);
      }
      validateSourceFigurePanelDimensions(panel, neutral);
    });
  }

  var sourcePresentationCache = new WeakMap();

  function sourcePresentationIndex(documentValue) {
    var value = ((documentValue || {}).metadata || {}).source_presentation;
    if (value === undefined) return null;
    if (sourcePresentationCache.has(documentValue)) {
      return sourcePresentationCache.get(documentValue);
    }
    if (
      !plainObject(value) ||
      Object.keys(value).sort().join(",") !==
        "blocks,captions,classifications,figures,schema_version,tables" ||
      value.schema_version !== "ac.document.source_presentation.v1" ||
      !Array.isArray(value.blocks) || !Array.isArray(value.classifications) ||
      !Array.isArray(value.captions) || !Array.isArray(value.figures) ||
      !Array.isArray(value.tables)
    ) throw new Error("source presentation metadata is invalid");
    var documentBlocks = documentValue.blocks || [];
    var presentable = documentBlocks.filter(function (block) {
      return ["heading", "paragraph", "list", "figure", "table"]
        .indexOf(block.kind) >= 0;
    });
    if (value.blocks.length !== presentable.length) {
      throw new Error("source presentation block coverage is invalid");
    }
    var blocks = new Map();
    value.blocks.forEach(function (entry, index) {
      var block = presentable[index];
      if (
        !plainObject(entry) ||
        Object.keys(entry).sort().join(",") !== "block_id,fields,roles" ||
        entry.block_id !== block.block_id || blocks.has(entry.block_id) ||
        !Array.isArray(entry.roles) || !Array.isArray(entry.fields) ||
        entry.roles.some(function (role) {
          return role !== "abstract" && role !== "classification" &&
            role !== "acknowledgements";
        }) || new Set(entry.roles).size !== entry.roles.length ||
        (entry.roles.length && block.kind !== "heading")
      ) throw new Error("source presentation block is invalid");
      blocks.set(entry.block_id, entry);
    });
    var blockById = new Map(documentBlocks.map(function (block) {
      return [block.block_id, block];
    }));
    var blockIndexById = new Map(documentBlocks.map(function (block, index) {
      return [block.block_id, index];
    }));
    var classificationByHeading = new Map();
    var classificationByValue = new Map();
    var previousClassificationIndex = -1;
    value.classifications.forEach(function (relation) {
      if (
        !plainObject(relation) || Object.keys(relation).sort().join(",") !==
          "classification_id,composition,heading_block_id,locator,separator," +
          "separator_source,value_block_ids" ||
        !/^classification-[0-9a-f]{24}$/.test(relation.classification_id) ||
        relation.composition !== "inline" || relation.separator !== ": " ||
        relation.separator_source !==
          "latexml_ar5iv_classification_after" ||
        !Array.isArray(relation.value_block_ids) ||
        !relation.value_block_ids.length ||
        !validateSourcePresentationLocator(
          relation.locator, ((documentValue.source || {}).source_format || "")
        )
      ) throw new Error("source classification presentation is invalid");
      var heading = blockById.get(relation.heading_block_id);
      var headingPresentation = blocks.get(relation.heading_block_id);
      var headingIndex = blockIndexById.get(relation.heading_block_id);
      if (
        !heading || heading.kind !== "heading" ||
        !headingPresentation ||
        headingPresentation.roles.join(",") !== "classification" ||
        !Number.isInteger(headingIndex) ||
        headingIndex <= previousClassificationIndex ||
        classificationByHeading.has(relation.heading_block_id) ||
        new Set(relation.value_block_ids).size !==
          relation.value_block_ids.length
      ) throw new Error("source classification heading is invalid");
      relation.value_block_ids.forEach(function (blockId, valueIndex) {
        var block = blockById.get(blockId);
        if (
          !normalizedNonblank(blockId) || !block || block.kind === "heading" ||
          blockIndexById.get(blockId) !== headingIndex + valueIndex + 1 ||
          classificationByValue.has(blockId) ||
          classificationByHeading.has(blockId)
        ) throw new Error("source classification value is invalid");
        classificationByValue.set(blockId, relation);
      });
      previousClassificationIndex = headingIndex;
      classificationByHeading.set(relation.heading_block_id, relation);
    });
    var captionBlocks = documentBlocks.filter(function (block) {
      if (block.kind !== "figure" && block.kind !== "table") return false;
      var blockPresentation = blocks.get(block.block_id);
      var captionField = blockPresentation && blockPresentation.fields.find(
        function (field) { return field.field === "caption"; }
      );
      return captionField && typeof captionField.text === "string" &&
        Boolean(captionField.text.trim());
    });
    if (value.captions.length !== captionBlocks.length) {
      throw new Error("source caption presentation coverage is invalid");
    }
    var captions = new Map();
    var captionAlignmentSources = {
      "class:ltx_centering": "center",
      "class:ltx_align_center": "center",
      "style:text-align:start": "start",
      "style:text-align:center": "center",
      "style:text-align:end": "end"
    };
    value.captions.forEach(function (entry, index) {
      var block = captionBlocks[index];
      if (
        !plainObject(entry) || Object.keys(entry).sort().join(",") !==
          "alignment,alignment_sources,block_id,kind,placement" ||
        entry.block_id !== block.block_id || entry.kind !== block.kind ||
        captions.has(entry.block_id) ||
        ["before_content", "after_content", "embedded"]
          .indexOf(entry.placement) < 0 ||
        (entry.kind === "figure" && entry.placement === "embedded") ||
        (entry.alignment !== null &&
          ["start", "center", "end"].indexOf(entry.alignment) < 0) ||
        !Array.isArray(entry.alignment_sources) ||
        (entry.alignment === null && entry.alignment_sources.length) ||
        (entry.alignment !== null && !entry.alignment_sources.length) ||
        new Set(entry.alignment_sources).size !==
          entry.alignment_sources.length ||
        entry.alignment_sources.some(function (source) {
          return captionAlignmentSources[source] !== entry.alignment;
        })
      ) throw new Error("source caption presentation is invalid");
      captions.set(entry.block_id, entry);
    });
    var figureTargets = sourceFigureTargetPanels(documentValue);
    var figureBlocks = documentBlocks.filter(function (block) {
      return block.kind === "figure" && figureTargets.has(block.block_id);
    });
    if (value.figures.length !== figureBlocks.length) {
      throw new Error("source Figure presentation coverage is invalid");
    }
    var figures = new Map();
    value.figures.forEach(function (entry, index) {
      var block = figureBlocks[index];
      if (
        !plainObject(entry) ||
        Object.keys(entry).sort().join(",") !== "block_id,layout,panels" ||
        entry.block_id !== block.block_id || figures.has(entry.block_id)
      ) throw new Error("source Figure presentation is invalid");
      validateSourceFigureLayout(entry, figureTargets.get(entry.block_id));
      figures.set(entry.block_id, entry);
    });
    var tableBlocks = documentBlocks.filter(function (block) {
      return block.kind === "table";
    });
    if (value.tables.length !== tableBlocks.length) {
      throw new Error("source Table presentation coverage is invalid");
    }
    var tables = new Map();
    value.tables.forEach(function (entry, index) {
      var block = tableBlocks[index];
      if (
        !plainObject(entry) ||
        Object.keys(entry).sort().join(",") !== "block_id,cells" ||
        entry.block_id !== block.block_id || tables.has(entry.block_id) ||
        !Array.isArray(entry.cells)
      ) throw new Error("source Table presentation is invalid");
      tables.set(entry.block_id, entry);
    });
    var indexed = {
      blocks: blocks,
      captions: captions,
      classificationByHeading: classificationByHeading,
      classificationByValue: classificationByValue,
      figures: figures,
      tables: tables,
      validatedBlocks: new Set(),
      validatedTables: new Set()
    };
    sourcePresentationCache.set(documentValue, indexed);
    return indexed;
  }

  function validateSourcePresentationLocator(locator, sourceFormat) {
    if (
      !plainObject(locator) || Object.keys(locator).sort().join(",") !==
        "column_end,column_start,line_end,line_start,selector,source_format," +
        "source_id" || locator.source_format !== sourceFormat
    ) return false;
    return ["line_start", "column_start", "line_end", "column_end"]
      .every(function (field) {
        return locator[field] === null ||
          (Number.isInteger(locator[field]) && locator[field] >= 0);
      }) && ["selector", "source_id"].every(function (field) {
        return typeof locator[field] === "string";
      });
  }

  function sourceClassificationForHeading(documentValue, blockId) {
    var indexed = sourcePresentationIndex(documentValue);
    return indexed ? indexed.classificationByHeading.get(blockId) || null : null;
  }

  function sourceClassificationForValue(documentValue, blockId) {
    var indexed = sourcePresentationIndex(documentValue);
    return indexed ? indexed.classificationByValue.get(blockId) || null : null;
  }

  function sourceCaptionPresentation(documentValue, blockId) {
    var indexed = sourcePresentationIndex(documentValue);
    if (!indexed) return null;
    var value = indexed.captions.get(blockId);
    if (!value) throw new Error("source caption presentation is missing");
    return value;
  }

  function sourceFigurePresentation(documentValue, blockId) {
    var indexed = sourcePresentationIndex(documentValue);
    if (!indexed) return null;
    var value = indexed.figures.get(blockId);
    if (!value) throw new Error("source Figure presentation is missing");
    return value;
  }

  function applySourceCaptionPresentation(node, presentation) {
    if (!node || !presentation) return;
    node.dataset.captionPlacement = presentation.placement;
    if (presentation.alignment !== null) {
      node.dataset.captionAlignment = presentation.alignment;
    }
  }

  function sourcePresentationBlock(documentValue, blockId) {
    var indexed = sourcePresentationIndex(documentValue);
    if (!indexed) return null;
    var value = indexed.blocks.get(blockId);
    if (!value) throw new Error("source presentation block is missing");
    if (!indexed.validatedBlocks.has(blockId)) {
      var sourceBlock = (documentValue.blocks || []).find(function (block) {
        return block.block_id === blockId;
      });
      if (!sourceBlock || !plainObject(sourceBlock.payload)) {
        throw new Error("source presentation block payload is not loaded");
      }
      var expected = sourcePresentationFieldKeys(sourceBlock);
      var actual = value.fields.map(function (field) {
        validateSourcePresentationField(sourceBlock, field);
        return sourcePresentationFieldKey(
          field.field, field.item_index, field.row_index, field.column_index
        );
      });
      if (
        actual.length !== expected.length || actual.some(function (key, index) {
          return key !== expected[index];
        })
      ) throw new Error("source presentation field coverage is invalid");
      indexed.validatedBlocks.add(blockId);
    }
    return value;
  }

  function sourcePresentationField(
    documentValue, blockId, field, itemIndex, rowIndex, columnIndex
  ) {
    var block = sourcePresentationBlock(documentValue, blockId);
    if (!block) return null;
    var key = sourcePresentationFieldKey(
      field, itemIndex, rowIndex, columnIndex
    );
    var values = block.fields.filter(function (entry) {
      return sourcePresentationFieldKey(
        entry.field, entry.item_index, entry.row_index, entry.column_index
      ) === key;
    });
    if (values.length !== 1) {
      throw new Error("source presentation field is missing or duplicate");
    }
    return values[0];
  }

  function sourceTablePresentation(documentValue, blockId) {
    var indexed = sourcePresentationIndex(documentValue);
    if (!indexed) return null;
    var value = indexed.tables.get(blockId);
    if (!value) throw new Error("source Table presentation is missing");
    if (!indexed.validatedTables.has(blockId)) {
      var sourceBlock = (documentValue.blocks || []).find(function (block) {
        return block.block_id === blockId;
      });
      if (!sourceBlock || !plainObject(sourceBlock.payload)) {
        throw new Error("source Table presentation payload is not loaded");
      }
      validateSourceTableCells(sourceBlock, value.cells);
      indexed.validatedTables.add(blockId);
    }
    return value;
  }

  function sourcePresentationFieldKey(
    field, itemIndex, rowIndex, columnIndex
  ) {
    return [field, itemIndex, rowIndex, columnIndex].map(function (value) {
      return value === null || value === undefined ? "" : String(value);
    }).join(":");
  }

  function sourcePresentationFieldKeys(block) {
    var payload = block.payload || {};
    if (block.kind === "heading" || block.kind === "paragraph") {
      return [sourcePresentationFieldKey("text", null, null, null)];
    }
    if (block.kind === "list") {
      return (payload.items || []).map(function (_item, itemIndex) {
        return sourcePresentationFieldKey(
          "list_item", itemIndex, null, null
        );
      });
    }
    if (block.kind === "figure") {
      return [sourcePresentationFieldKey("caption", null, null, null)];
    }
    if (block.kind === "table") {
      return [sourcePresentationFieldKey("caption", null, null, null)]
        .concat((payload.headers || []).map(function (_value, columnIndex) {
          return sourcePresentationFieldKey(
            "table_header", null, null, columnIndex
          );
        })).concat((payload.rows || []).flatMap(function (row, rowIndex) {
          return row.map(function (_value, columnIndex) {
            return sourcePresentationFieldKey(
              "table_cell", null, rowIndex, columnIndex
            );
          });
        }));
    }
    return [];
  }

  function validateSourcePresentationField(block, field) {
    if (
      !plainObject(field) || Object.keys(field).sort().join(",") !==
        "column_index,field,inline_spans,item_index,marks,row_index,text" ||
      typeof field.text !== "string" || !Array.isArray(field.inline_spans) ||
      !Array.isArray(field.marks)
    ) throw new Error("source presentation field is invalid");
    var key = sourcePresentationFieldKey(
      field.field, field.item_index, field.row_index, field.column_index
    );
    var payload = block.payload || {};
    var expected;
    if (key === sourcePresentationFieldKey("text", null, null, null)) {
      expected = payload.text;
    } else if (field.field === "list_item" && Number.isInteger(field.item_index)) {
      expected = ((payload.items || [])[field.item_index] || {}).text;
    } else if (key === sourcePresentationFieldKey("caption", null, null, null)) {
      expected = payload.caption;
    } else if (
      field.field === "table_header" && Number.isInteger(field.column_index)
    ) {
      expected = (payload.headers || [])[field.column_index];
    } else if (
      field.field === "table_cell" && Number.isInteger(field.row_index) &&
      Number.isInteger(field.column_index)
    ) {
      expected = ((payload.rows || [])[field.row_index] || [])[field.column_index];
    }
    if (field.text !== expected) {
      throw new Error(
        "source presentation field differs from its block: " +
        block.block_id + " " + key
      );
    }
    validateSourcePresentationSpans(field.inline_spans, field.text);
    validateSourcePresentationMarks(field.marks, field.text);
  }

  function validateSourcePresentationSpans(spans, text) {
    var cursor = 0;
    var reconstructed = "";
    spans.forEach(function (span) {
      if (!plainObject(span) || ["text", "link", "math"].indexOf(span.kind) < 0) {
        throw new Error("source presentation inline span is invalid");
      }
      var fields = span.kind === "text" ? "end,kind,start,text" :
        span.kind === "link" ? "end,kind,start,target,text" :
          "end,kind,source,start,tex,text";
      if (
        Object.keys(span).sort().join(",") !== fields ||
        !Number.isInteger(span.start) || !Number.isInteger(span.end) ||
        typeof span.text !== "string" || span.start !== cursor ||
        span.end <= span.start ||
        span.end - span.start !== Array.from(span.text).length ||
        (span.kind === "link" && !normalizedNonblank(span.target)) ||
        (span.kind === "math" &&
          (!normalizedNonblank(span.tex) || !normalizedNonblank(span.source)))
      ) throw new Error("source presentation inline span is invalid");
      cursor = span.end;
      reconstructed += span.text;
    });
    if (reconstructed !== text) {
      throw new Error("source presentation inline spans do not reconstruct text");
    }
  }

  function validateSourcePresentationMarks(marks, text) {
    var length = Array.from(text).length;
    var seen = new Set();
    marks.forEach(function (mark) {
      if (
        !plainObject(mark) ||
        Object.keys(mark).sort().join(",") !== "end,kind,start" ||
        (mark.kind !== "strong" && mark.kind !== "emphasis") ||
        !Number.isInteger(mark.start) || !Number.isInteger(mark.end) ||
        mark.start < 0 || mark.start >= mark.end || mark.end > length
      ) throw new Error("source presentation mark is invalid");
      var identity = [mark.kind, mark.start, mark.end].join(":");
      if (seen.has(identity)) {
        throw new Error("source presentation mark is duplicate");
      }
      seen.add(identity);
    });
  }

  function validateSourceTableCells(block, cells) {
    var payload = block.payload || {};
    var headerOffset = (payload.headers || []).length ? 1 : 0;
    var height = headerOffset + (payload.rows || []).length;
    var width = Math.max(
      (payload.headers || []).length,
      0
    );
    (payload.rows || []).forEach(function (row) {
      width = Math.max(width, row.length);
    });
    var occupied = new Set();
    var origins = new Set();
    var alignmentSources = {
      "class:ltx_align_left": "left",
      "class:ltx_align_center": "center",
      "class:ltx_align_right": "right",
      "style:text-align:left": "left",
      "style:text-align:center": "center",
      "style:text-align:right": "right",
      "style:text-align:start": "start",
      "style:text-align:end": "end"
    };
    var ruleSources = {
      "class:ltx_border_t": "top",
      "class:ltx_border_tt": "top",
      "class:ltx_border_T": "top",
      "class:ltx_border_r": "right",
      "class:ltx_border_rr": "right",
      "class:ltx_border_R": "right",
      "class:ltx_border_r_dashed": "right",
      "class:ltx_border_b": "bottom",
      "class:ltx_border_bb": "bottom",
      "class:ltx_border_B": "bottom",
      "class:ltx_border_b_dashed": "bottom",
      "class:ltx_border_l": "left",
      "class:ltx_border_ll": "left",
      "class:ltx_border_L": "left"
    };
    var edgeOrder = {top: 0, right: 1, bottom: 2, left: 3};
    cells.forEach(function (cell) {
      if (
        !plainObject(cell) || Object.keys(cell).sort().join(",") !==
          "column_index,column_span,horizontal_alignment," +
          "horizontal_alignment_sources,kind,locator,row_index,row_span," +
          "rule_edges" ||
        !Number.isInteger(cell.row_index) ||
        !Number.isInteger(cell.column_index) ||
        !Number.isInteger(cell.row_span) ||
        !Number.isInteger(cell.column_span) ||
        cell.row_index < 0 || cell.column_index < 0 ||
        cell.row_span < 1 || cell.column_span < 1 ||
        cell.row_index + cell.row_span > height ||
        cell.column_index + cell.column_span > width ||
        (cell.kind !== "header" && cell.kind !== "data") ||
        !plainObject(cell.locator) ||
        !Array.isArray(cell.horizontal_alignment_sources) ||
        !Array.isArray(cell.rule_edges)
      ) throw new Error("source Table cell geometry is invalid");
      var alignment = cell.horizontal_alignment;
      if (
        alignment === null ? cell.horizontal_alignment_sources.length !== 0 :
          ["left", "center", "right", "start", "end"]
            .indexOf(alignment) < 0 ||
          !cell.horizontal_alignment_sources.length ||
          new Set(cell.horizontal_alignment_sources).size !==
            cell.horizontal_alignment_sources.length ||
          cell.horizontal_alignment_sources.some(function (source) {
            return alignmentSources[source] !== alignment;
          })
      ) throw new Error("source Table cell alignment is invalid");
      var previousEdge = -1;
      var seenEdges = new Set();
      cell.rule_edges.forEach(function (rule) {
        if (
          !plainObject(rule) || Object.keys(rule).sort().join(",") !==
            "edge,source" || edgeOrder[rule.edge] === undefined ||
          !normalizedNonblank(rule.source) || seenEdges.has(rule.edge) ||
          edgeOrder[rule.edge] <= previousEdge ||
          ruleSources[rule.source] !== rule.edge
        ) throw new Error("source Table cell rule edge is invalid");
        seenEdges.add(rule.edge);
        previousEdge = edgeOrder[rule.edge];
      });
      var origin = cell.row_index + ":" + cell.column_index;
      if (origins.has(origin)) {
        throw new Error("source Table cell origin is duplicate");
      }
      origins.add(origin);
      for (
        var row = cell.row_index;
        row < cell.row_index + cell.row_span;
        row += 1
      ) {
        for (
          var column = cell.column_index;
          column < cell.column_index + cell.column_span;
          column += 1
        ) {
          var point = row + ":" + column;
          if (occupied.has(point)) {
            throw new Error("source Table cell geometry overlaps");
          }
          occupied.add(point);
        }
      }
    });
  }

  function sourceFrontMatterEntries(documentValue) {
    var value = ((documentValue || {}).metadata || {}).source_front_matter;
    if (value === undefined) return [];
    if (
      !value || value.schema_version !== "ac.document.source_front_matter.v1" ||
      !Array.isArray(value.entries)
    ) throw new Error("source front matter metadata is invalid");
    return value.entries.slice();
  }

  function sourceFrontMatterAt(documentValue, blockIndex) {
    return sourceFrontMatterEntries(documentValue).filter(function (entry) {
      return entry && entry.kind === "authors" &&
        Number.isInteger(entry.block_index) && entry.block_index === blockIndex &&
        !sourceFrontMatterPromotedToHeader(documentValue, entry);
    });
  }

  function sourceFrontMatterPromotedToHeader(documentValue, entry) {
    var first = (documentValue.blocks || [])[0] || {};
    return entry && entry.kind === "authors" && entry.block_index === 1 &&
      first.kind === "heading" && Number((first.payload || {}).level) === 1;
  }

  function sourceNotes(documentValue) {
    var value = ((documentValue || {}).metadata || {}).source_notes;
    if (value === undefined) return [];
    if (
      !value || value.schema_version !== "ac.document.source_notes.v1" ||
      !Array.isArray(value.notes)
    ) throw new Error("source note metadata is invalid");
    return value.notes.slice();
  }

  function registerSourceNoteNavigationTargets(documentValue) {
    sourceNotes(documentValue).forEach(function (note) {
      if (!note || !normalizedNonblank(note.note_id) ||
        !normalizedNonblank(note.owner_block_id)) {
        throw new Error("source note navigation identity is invalid");
      }
      var ownerTarget = "block-" + safeToken(note.owner_block_id);
      var chunk = state.chunkByTargetId.get(ownerTarget);
      if (!chunk) throw new Error("source note owner render chunk is missing");
      [
        "source-note-",
        "source-note-ref-",
        "translation-note-ref-"
      ].forEach(function (prefix) {
        state.chunkByTargetId.set(prefix + safeToken(note.note_id), chunk);
      });
    });
  }

  function sourceNoteById(documentValue) {
    var values = new Map();
    sourceNotes(documentValue).forEach(function (note) {
      if (!note || !normalizedNonblank(note.note_id) || values.has(note.note_id)) {
        throw new Error("source note identity is invalid");
      }
      values.set(note.note_id, note);
    });
    return values;
  }

  function sourceNotesForBlock(documentValue, blockId) {
    return sourceNotes(documentValue).filter(function (note) {
      return note && note.owner_block_id === blockId;
    }).sort(function (left, right) {
      return Number(left.ordinal) - Number(right.ordinal);
    });
  }

  function sourceNoteTranslationId(documentValue, revision) {
    var provenance = revision && revision.provenance || {};
    var contract = provenance.source_note_translation;
    if (contract === undefined) return "";
    if (
      !plainObject(contract) ||
      Object.keys(contract).sort().join(",") !== "note_id,schema_version" ||
      contract.schema_version !== "alc.render.source_note_translation.v1" ||
      !normalizedNonblank(contract.note_id)
    ) throw new Error("source note translation provenance is invalid");
    var note = sourceNoteById(documentValue).get(contract.note_id);
    var anchor = revision && revision.anchor || {};
    var related = anchor.related_blocks;
    if (
      !note || revision.role !== "translation" || anchor.kind !== "block" ||
      anchor.target_id !== note.owner_block_id || !Array.isArray(related) ||
      related.length !== 1 || related[0].block_id !== note.owner_block_id
    ) throw new Error("source note translation anchor differs from its owner");
    return contract.note_id;
  }

  function sourceNoteTranslations(documentValue, revisions) {
    var values = new Map();
    var fragments = revisions || Array.from(state.selected.values());
    Array.from(fragments).forEach(function (revision) {
      if (!fragmentIsVisible(revision)) return;
      var noteId = sourceNoteTranslationId(documentValue, revision);
      if (!noteId) return;
      if (values.has(noteId)) {
        throw new Error("source note translation has multiple selected fragments");
      }
      values.set(noteId, revision);
    });
    return values;
  }

  function sourceNotesForAnchor(block, field, itemIndex, rowIndex, columnIndex) {
    var documentValue = state.payload.publication.source_document;
    return sourceNotesForBlock(documentValue, block.block_id).filter(function (note) {
      var anchor = note.anchor || {};
      return anchor.field === field && anchor.item_index === itemIndex &&
        anchor.row_index === rowIndex && anchor.column_index === columnIndex;
    });
  }

  function documentNotesBefore(blockId) {
    var metadata = state.payload.publication.source_document.metadata || {};
    var notes = metadata.document_notes || {};
    if (
      notes.schema_version === "ac.document.document_notes.v1" &&
      Array.isArray(notes.items)
    ) {
      return notes.items.filter(function (item) {
        return item && item.before_block_id === blockId &&
          (item.kind === "metadata" ||
            (item.kind === "source_page" &&
              Number.isInteger(item.page_number) && item.page_number > 0));
      });
    }
    var boundaries = metadata.source_page_boundaries || {};
    if (
      boundaries.schema_version !== "ac.document.source_page_boundaries.v1" ||
      !Array.isArray(boundaries.items)
    ) return [];
    return boundaries.items.filter(function (item) {
      return item && item.before_block_id === blockId &&
        Number.isInteger(item.page_number) && item.page_number > 0;
    }).map(function (item) {
      return {
        kind: "source_page",
        text: "",
        page_number: item.page_number,
        before_block_id: item.before_block_id
      };
    });
  }

  function renderDocumentNote(item) {
    var isPage = item.kind === "source_page";
    var text = isPage ?
      labels().documentPage + " · " + item.page_number : String(item.text || "");
    var note = element("aside", "ac-document-data-note", text);
    note.dataset.documentDataKind = item.kind;
    if (isPage) note.dataset.pageNumber = String(item.page_number);
    note.setAttribute("aria-label", labels().documentData);
    return note;
  }

  function effectiveReaderHeadingLevel(block, presentation) {
    void presentation;
    var payload = block.payload || {};
    return Math.max(2, Math.min(6, Number(payload.level) + 1));
  }

  function appendSourceClassificationValues(
    parent, relation, documentValue
  ) {
    relation.value_block_ids.forEach(function (blockId, index) {
      var valueBlock = (documentValue.blocks || []).find(function (candidate) {
        return candidate.block_id === blockId;
      });
      if (!valueBlock || !plainObject(valueBlock.payload)) {
        throw new Error("source classification value payload is not loaded");
      }
      if (index) parent.appendChild(document.createTextNode(" "));
      var value = element("span", "alc-source-classification-value");
      value.id = "block-" + safeToken(valueBlock.block_id);
      value.dataset.blockId = valueBlock.block_id;
      value.appendChild(renderSourceBlock(valueBlock));
      parent.appendChild(value);
    });
  }

  function renderSourceBlock(block) {
    var payload = block.payload || {};
    var container = document.createDocumentFragment();
    var documentValue = state.payload.publication.source_document;
    if (block.kind === "heading") {
      var headingPresentation = sourcePresentationBlock(
        documentValue, block.block_id
      );
      var level = effectiveReaderHeadingLevel(block, headingPresentation);
      var heading = element("h" + level);
      heading.id = "heading-" + safeToken(block.block_id);
      var headingView = sourcePresentationField(
        documentValue, block.block_id, "text", null, null, null
      );
      if (headingView) {
        appendInlineSpans(
          heading, headingView.inline_spans, headingView.text, [],
          headingView.marks
        );
      } else {
        heading.textContent = payload.text || "";
      }
      var classification = sourceClassificationForHeading(
        documentValue, block.block_id
      );
      if (classification) {
        var composition = element("div", "alc-source-classification-composition");
        composition.appendChild(heading);
        composition.appendChild(element(
          "span", "alc-source-classification-separator",
          classification.separator
        ));
        appendSourceClassificationValues(
          composition, classification, documentValue
        );
        container.appendChild(composition);
      } else {
        container.appendChild(heading);
      }
      removeVisibleHtmlTags(heading);
      decorateGlossary(heading, "source");
      return container;
    }
    if (block.kind === "paragraph") {
      var paragraph = element("p");
      var paragraphView = sourcePresentationField(
        documentValue, block.block_id, "text", null, null, null
      );
      appendInlineSpans(
        paragraph,
        paragraphView ? paragraphView.inline_spans : payload.inline_spans,
        paragraphView ? paragraphView.text : payload.text,
        sourceNotesForAnchor(block, "text", null, null, null),
        paragraphView ? paragraphView.marks : []
      );
      container.appendChild(paragraph);
      return container;
    }
    if (block.kind === "list") {
      if (listPathEntries(block).length) {
        var ownedItem = (payload.items || [])[0] || {};
        var ownedItemView = sourcePresentationField(
          documentValue, block.block_id, "list_item", 0, null, null
        );
        var segment = element("p", "alc-list-segment");
        if (sourceBibliographyItemIndexes(block.block_id).has(0)) {
          segment.id = sourceReferenceTargetId(block.block_id, 0);
          segment.classList.add(
            "alc-source-reference-target", "alc-source-navigation-target"
          );
          segment.tabIndex = -1;
        }
        appendInlineSpans(
          segment,
          ownedItemView ? ownedItemView.inline_spans : ownedItem.inline_spans,
          ownedItemView ? ownedItemView.text : ownedItem.text,
          sourceNotesForAnchor(block, "list_item", 0, null, null),
          ownedItemView ? ownedItemView.marks : []
        );
        container.appendChild(segment);
        return container;
      }
      var list = element(payload.ordered ? "ol" : "ul");
      (payload.items || []).forEach(function (item, itemIndex) {
        var listItem = element("li");
        var listItemView = sourcePresentationField(
          documentValue, block.block_id, "list_item", itemIndex, null, null
        );
        if (
          sourceBibliographyItemIndexes(block.block_id).has(itemIndex)
        ) {
          listItem.id = sourceReferenceTargetId(block.block_id, itemIndex);
          listItem.className =
            "alc-source-reference-target alc-source-navigation-target";
          listItem.tabIndex = -1;
        }
        appendInlineSpans(
          listItem,
          listItemView ? listItemView.inline_spans : item.inline_spans,
          listItemView ? listItemView.text : item.text,
          sourceNotesForAnchor(block, "list_item", itemIndex, null, null),
          listItemView ? listItemView.marks : []
        );
        list.appendChild(listItem);
      });
      container.appendChild(list);
      return container;
    }
    if (block.kind === "code") {
      var pre = element("pre");
      var code = element("code", "", payload.text || "");
      if (payload.language) code.dataset.language = payload.language;
      pre.appendChild(code);
      container.appendChild(pre);
      return container;
    }
    if (block.kind === "equation") {
      var math = element("div", "math math-display", payload.tex || "");
      math.dataset.tex = payload.tex || "";
      var equationLabel = effectiveEquationLabel(block, payload);
      container.appendChild(equationRow(math, equationLabel));
      removeVisibleHtmlTags(container);
      typeset(container);
      return container;
    }
    if (block.kind === "table") {
      container.appendChild(renderSourceTableBlock(
        block, payload, documentValue
      ));
      return container;
    }
    if (block.kind === "figure") {
      var figure = element("figure");
      var figureCaption = null;
      var figureCaptionPresentation = payload.caption ?
        sourceCaptionPresentation(documentValue, block.block_id) : null;
      if (payload.caption) {
        figureCaption = element("figcaption", "alc-figure-caption");
        var figureCaptionView = sourcePresentationField(
          documentValue, block.block_id, "caption", null, null, null
        );
        appendInlineSpans(
          figureCaption,
          figureCaptionView ? figureCaptionView.inline_spans : [],
          figureCaptionView ? figureCaptionView.text : payload.caption,
          [], figureCaptionView ? figureCaptionView.marks : []
        );
        applySourceCaptionPresentation(
          figureCaption, figureCaptionPresentation
        );
        if (
          figureCaptionPresentation &&
          figureCaptionPresentation.placement === "before_content"
        ) figure.appendChild(figureCaption);
      }
      var panels = sourceFigurePanels(block);
      if (panels.length) {
        var panelRoot = element("div", "alc-figure-panels");
        panelRoot.dataset.panelCount = String(panels.length);
        var figurePresentation = sourceFigurePresentation(
          documentValue, block.block_id
        );
        var availablePanels = 0;
        if (
          figurePresentation &&
          figurePresentation.layout.kind !== "neutral"
        ) {
          panelRoot.dataset.layoutKind = figurePresentation.layout.kind;
          panelRoot.dataset.layoutColumns = String(
            figurePresentation.layout.column_count
          );
          panelRoot.dataset.layoutRows = String(
            figurePresentation.layout.row_count
          );
          panelRoot.dataset.columnSource =
            figurePresentation.layout.column_source || "";
          figurePresentation.layout.rows.forEach(function (
            panelIndexes, rowIndex
          ) {
            var panelRow = element("div", "alc-figure-panel-row");
            var rowSource =
              figurePresentation.layout.row_sources[rowIndex];
            panelRow.dataset.columnSource = rowSource;
            panelRow.dataset.authoredColumnCount = String(
              panelIndexes.length
            );
            panelRow.style.setProperty(
              "--alc-figure-authored-row-columns",
              String(panelIndexes.length)
            );
            if (rowSource === "class:ltx_flex_size_2") {
              panelRow.dataset.responsiveWrapProfile =
                "latexml_ar5iv_flex_size_2";
              panelRow.style.setProperty(
                "--alc-figure-row-panel-min", "20rem"
              );
            }
            panelIndexes.forEach(function (panelIndex) {
              var descriptor = figurePresentation.panels[panelIndex];
              var panel = panels[panelIndex];
              var image = renderSourceFigurePanelImage(
                panel, descriptor, payload
              );
              if (!image) {
                var placeholder = element(
                  "span", "alc-figure-panel-placeholder"
                );
                placeholder.dataset.panelIndex = String(panelIndex);
                placeholder.setAttribute("aria-hidden", "true");
                if (descriptor && descriptor.aspect_ratio !== null) {
                  placeholder.style.aspectRatio =
                    descriptor.aspect_ratio.join(" / ");
                }
                panelRow.appendChild(placeholder);
                return;
              }
              panelRow.appendChild(image);
              availablePanels += 1;
            });
            panelRoot.appendChild(panelRow);
          });
        } else {
          panelRoot.dataset.layoutKind = "neutral";
          panels.forEach(function (panel, panelIndex) {
            var descriptor = figurePresentation ?
              figurePresentation.panels[panelIndex] : null;
            var image = renderSourceFigurePanelImage(
              panel, descriptor, payload
            );
            if (!image) return;
            panelRoot.appendChild(image);
            availablePanels += 1;
          });
        }
        panelRoot.dataset.availablePanelCount = String(availablePanels);
        if (availablePanels) figure.appendChild(panelRoot);
      } else {
        var digest = payload.asset_digest || "";
        var resource = resourceForDigest(digest);
        if (resource) {
          var image = element("img");
          image.src = resource.data_uri;
          image.alt = payload.alt_text || "";
          figure.appendChild(image);
        } else {
          figure.appendChild(element(
            "p", "alc-figure-note", payload.alt_text || payload.logical_name || ""
          ));
        }
      }
      if (
        figureCaption && (!figureCaptionPresentation ||
          figureCaptionPresentation.placement === "after_content")
      ) {
        figure.appendChild(figureCaption);
      }
      container.appendChild(figure);
      removeVisibleHtmlTags(figure);
      decorateGlossary(figure, "source");
      return container;
    }
    container.appendChild(element("p", "", JSON.stringify(payload)));
    removeVisibleHtmlTags(container);
    return container;
  }

  function renderSourceFigurePanelImage(panel, descriptor, payload) {
    if (panel.status !== "available") return null;
    var panelResource = resourceForDigest(panel.asset_digest || "");
    if (!panelResource) {
      throw new Error("available source Figure panel resource is missing");
    }
    var panelImage = element("img", "alc-figure-panel");
    panelImage.src = panelResource.data_uri;
    panelImage.alt = panel.alt_text || payload.alt_text ||
      payload.caption || panel.logical_name || "";
    panelImage.dataset.panelIndex = String(panel.panel_index);
    panelImage.dataset.artifactDigest = String(panel.asset_digest || "");
    panelImage.dataset.sourceId = String(panel.source_id || "");
    if (descriptor && descriptor.display_width !== null) {
      panelImage.dataset.panelDisplayWidth = String(descriptor.display_width);
    }
    if (descriptor && descriptor.aspect_ratio !== null) {
      panelImage.style.aspectRatio = descriptor.aspect_ratio.join(" / ");
    }
    return panelImage;
  }

  function renderSourceTableBlock(block, payload, documentValue) {
    var presentation = sourceTablePresentation(documentValue, block.block_id);
    var captionPresentation = payload.caption ?
      sourceCaptionPresentation(documentValue, block.block_id) : null;
    var placement = captionPresentation ? captionPresentation.placement :
      "before_content";
    var figure = element("figure", "alc-table-figure");
    var table = element("table");
    var caption = null;
    if (payload.caption) {
      caption = element(
        placement === "embedded" ? "caption" : "figcaption",
        "alc-table-caption"
      );
      var captionView = sourcePresentationField(
        documentValue, block.block_id, "caption", null, null, null
      );
      appendInlineSpans(
        caption, captionView ? captionView.inline_spans : [],
        captionView ? captionView.text : payload.caption, [],
        captionView ? captionView.marks : []
      );
      applySourceCaptionPresentation(caption, captionPresentation);
      if (placement !== "embedded") {
        caption.id = "table-caption-" + safeToken(block.block_id);
        table.setAttribute("aria-labelledby", caption.id);
      }
    }
    if (caption && placement === "before_content") figure.appendChild(caption);
    if (caption && placement === "embedded") table.appendChild(caption);
    if (presentation) {
      table.classList.add("alc-source-presentation-table");
      renderSourcePresentationTableRows(
        table, block, payload, documentValue, presentation
      );
    } else {
      renderLegacySourceTableRows(table, block, payload);
    }
    figure.appendChild(table);
    if (caption && placement === "after_content") figure.appendChild(caption);
    removeVisibleHtmlTags(figure);
    decorateGlossary(figure, "source");
    return figure;
  }

  function identifySourceTableCell(cell, field, rowIndex, columnIndex) {
    cell.dataset.sourceField = field;
    if (rowIndex !== null) {
      cell.dataset.sourceRowIndex = String(rowIndex);
    }
    cell.dataset.sourceColumnIndex = String(columnIndex);
  }

  function applySourceTableCellPresentation(cell, geometry) {
    if (geometry.horizontal_alignment !== null) {
      cell.dataset.tableHorizontalAlignment = geometry.horizontal_alignment;
    }
    geometry.rule_edges.forEach(function (rule) {
      var suffix = rule.edge.charAt(0).toUpperCase() + rule.edge.slice(1);
      cell.dataset["tableRule" + suffix] = "true";
    });
  }

  function renderLegacySourceTableRows(table, block, payload) {
    if ((payload.headers || []).length) {
      var head = element("thead");
      var headerRow = element("tr");
      payload.headers.forEach(function (value, columnIndex) {
        var header = element("th");
        identifySourceTableCell(
          header, "table_header", null, columnIndex
        );
        appendInlineSpans(
          header, [], value,
          sourceNotesForAnchor(
            block, "table_header", null, null, columnIndex
          )
        );
        headerRow.appendChild(header);
      });
      head.appendChild(headerRow);
      table.appendChild(head);
    }
    var body = element("tbody");
    (payload.rows || []).forEach(function (values, rowIndex) {
      var tr = element("tr");
      values.forEach(function (value, columnIndex) {
        var cell = element("td");
        identifySourceTableCell(
          cell, "table_cell", rowIndex, columnIndex
        );
        appendInlineSpans(
          cell, [], value,
          sourceNotesForAnchor(
            block, "table_cell", null, rowIndex, columnIndex
          )
        );
        tr.appendChild(cell);
      });
      body.appendChild(tr);
    });
    table.appendChild(body);
  }

  function renderSourcePresentationTableRows(
    table, block, payload, documentValue, presentation
  ) {
    var headerOffset = (payload.headers || []).length ? 1 : 0;
    var cellsByRow = new Map();
    presentation.cells.forEach(function (cell) {
      var row = cellsByRow.get(cell.row_index) || [];
      row.push(cell);
      cellsByRow.set(cell.row_index, row);
    });
    function appendRow(parent, gridRow) {
      var tr = element("tr");
      (cellsByRow.get(gridRow) || []).sort(function (left, right) {
        return left.column_index - right.column_index;
      }).forEach(function (geometry) {
        var isHeaderField = headerOffset && gridRow === 0;
        var rowIndex = isHeaderField ? null : gridRow - headerOffset;
        var field = isHeaderField ? "table_header" : "table_cell";
        var view = sourcePresentationField(
          documentValue, block.block_id, field, null, rowIndex,
          geometry.column_index
        );
        var cell = element(geometry.kind === "header" ? "th" : "td");
        identifySourceTableCell(
          cell, field, rowIndex, geometry.column_index
        );
        applySourceTableCellPresentation(cell, geometry);
        if (geometry.row_span > 1) cell.rowSpan = geometry.row_span;
        if (geometry.column_span > 1) cell.colSpan = geometry.column_span;
        if (geometry.kind === "header") {
          cell.scope = isHeaderField ? "col" : "row";
        }
        appendInlineSpans(
          cell, view.inline_spans, view.text,
          sourceNotesForAnchor(
            block, field, null, rowIndex, geometry.column_index
          ), view.marks
        );
        tr.appendChild(cell);
      });
      parent.appendChild(tr);
    }
    if (headerOffset) {
      var head = element("thead");
      appendRow(head, 0);
      table.appendChild(head);
    }
    var body = element("tbody");
    (payload.rows || []).forEach(function (_row, rowIndex) {
      appendRow(body, rowIndex + headerOffset);
    });
    table.appendChild(body);
  }

  function effectiveEquationLabel(block, payload) {
    var documentValue = state.payload.publication.source_document;
    var reconciliations = (
      (documentValue.metadata || {}).equation_label_reconciliation || {}
    );
    var reconciliation = reconciliations[block.block_id];
    if (
      reconciliation &&
      typeof reconciliation.effective_label === "string" &&
      reconciliation.effective_label.trim()
    ) {
      return reconciliation.effective_label.trim();
    }
    return typeof payload.label === "string" ? payload.label.trim() : "";
  }

  function equationRow(math, label) {
    var row = element("div", "alc-equation-row");
    if (math.parentElement) math.replaceWith(row);
    row.appendChild(math);
    var visibleLabel = displayEquationLabel(label);
    if (visibleLabel) {
      row.appendChild(element("span", "alc-equation-label", visibleLabel));
    }
    return row;
  }

  function displayEquationLabel(label) {
    var value = String(label || "").trim();
    if (!value) return "";
    return value.charAt(0) === "(" && value.charAt(value.length - 1) === ")" ?
      value : "(" + value + ")";
  }

  function appendInlineSpanSlice(parent, span, start, end) {
    if (end <= start) return;
    var text = Array.from(String(span.text || "")).slice(start, end).join("");
    if (span.kind === "math") {
      if (start !== 0 || end !== Array.from(String(span.text || "")).length) {
        throw new Error("source note anchor splits an inline math span");
      }
      var math = element("span", "math math-inline", span.source || span.tex || text);
      math.dataset.tex = span.tex || span.source || text;
      parent.appendChild(math);
    } else if (span.kind === "link") {
      var link = element("a", "", text || span.target || "");
      link.href = span.target || "";
      link.rel = "noopener noreferrer";
      parent.appendChild(link);
    } else {
      parent.appendChild(document.createTextNode(text));
    }
  }

  function appendMarkedInlineSpanSlice(
    parent, span, spanStart, start, end, marks
  ) {
    if (end <= start) return;
    var target = parent;
    marks.filter(function (mark) {
      return mark.start <= start && mark.end >= end;
    }).sort(function (left, right) {
      return left.start - right.start || right.end - left.end ||
        (left.kind === "strong" ? -1 : 1);
    }).forEach(function (mark) {
      var wrapper = element(mark.kind === "strong" ? "strong" : "em");
      target.appendChild(wrapper);
      target = wrapper;
    });
    appendInlineSpanSlice(target, span, start - spanStart, end - spanStart);
  }

  function renderSourceNoteReference(note) {
    var marker = String(note.marker || "");
    var reference = element("sup", "alc-source-note-ref");
    reference.id = "source-note-ref-" + safeToken(note.note_id);
    var link = element("a", "", marker);
    link.href = "#source-note-" + safeToken(note.note_id);
    link.setAttribute("aria-label", labels().sourceNote + " " + marker);
    reference.appendChild(link);
    return reference;
  }

  function renderTranslationSourceNoteReference(note) {
    var marker = String(note.marker || "");
    var reference = element(
      "sup", "alc-source-note-ref alc-translation-note-ref"
    );
    reference.id = "translation-note-ref-" + safeToken(note.note_id);
    var link = element("a", "", marker);
    link.href = "#source-note-" + safeToken(note.note_id);
    link.setAttribute("aria-label", labels().sourceNote + " " + marker);
    reference.appendChild(link);
    return reference;
  }

  function appendInlineSpans(
    parent, spans, fallback, sourceNoteValues, sourceMarks
  ) {
    var text = String(fallback || "");
    var values = Array.isArray(spans) && spans.length ? spans.slice() : [{
      kind: "text", start: 0, end: Array.from(text).length, text: text
    }];
    var notes = Array.isArray(sourceNoteValues) ? sourceNoteValues.slice() : [];
    var marks = Array.isArray(sourceMarks) ? sourceMarks.slice() : [];
    notes.sort(function (left, right) {
      return Number((left.anchor || {}).start) - Number((right.anchor || {}).start);
    });
    var markBoundaries = new Set();
    marks.forEach(function (mark) {
      markBoundaries.add(Number(mark.start));
      markBoundaries.add(Number(mark.end));
    });
    var noteIndex = 0;
    values.forEach(function (span) {
      var spanText = String(span.text || "");
      var spanStart = Number(span.start);
      var spanEnd = Number(span.end);
      if (
        !Number.isInteger(spanStart) || !Number.isInteger(spanEnd) ||
        spanEnd - spanStart !== Array.from(spanText).length
      ) throw new Error("source inline span range is invalid");
      var cursor = spanStart;
      while (cursor < spanEnd) {
        var note = noteIndex < notes.length ? notes[noteIndex] : null;
        var anchor = note && note.anchor || {};
        var noteStart = note ? Number(anchor.start) : spanEnd;
        var noteEnd = note ? Number(anchor.end) : spanEnd;
        if (note && noteStart < cursor) {
          throw new Error("source note anchor is outside inline content");
        }
        if (note && noteStart === cursor && noteStart < spanEnd) {
          if (
            !Number.isInteger(noteStart) || !Number.isInteger(noteEnd) ||
            noteEnd > spanEnd || noteEnd <= noteStart ||
            Array.from(spanText).slice(
              noteStart - spanStart, noteEnd - spanStart
            ).join("") !== note.marker
          ) throw new Error("source note anchor differs from inline content");
          parent.appendChild(renderSourceNoteReference(note));
          cursor = noteEnd;
          noteIndex += 1;
          continue;
        }
        var next = Math.min(spanEnd, noteStart);
        markBoundaries.forEach(function (boundary) {
          if (boundary > cursor && boundary < next) next = boundary;
        });
        if (next <= cursor) {
          throw new Error("source presentation inline boundary is invalid");
        }
        appendMarkedInlineSpanSlice(
          parent, span, spanStart, cursor, next, marks
        );
        cursor = next;
      }
    });
    if (noteIndex !== notes.length) {
      throw new Error("source note anchor is outside inline content");
    }
    removeVisibleHtmlTags(parent);
    decorateLegacyBibliographyLinks(parent);
    decorateLegacyStructuralLinks(parent);
    decorateGlossary(parent, "source");
    typeset(parent);
  }

  function resourceForDigest(digest) {
    return hydrateResource(
      ensureSourceIndexes().resourcesByDigest.get(digest) || null
    );
  }

  function resourceForLogicalName(logicalName) {
    return hydrateResource(
      ensureSourceIndexes().resourcesByLogicalName.get(logicalName) || null
    );
  }

  function sourceFigurePanels(block) {
    if (!block || block.kind !== "figure") return [];
    var documentValue = state.payload && state.payload.publication &&
      state.payload.publication.source_document || {};
    var manifest = (documentValue.metadata || {}).source_target_manifest || {};
    if (
      manifest.schema_version !== "ac.document.source_target_manifest.v1" ||
      !Array.isArray(manifest.targets)
    ) return [];
    var candidates = manifest.targets.filter(function (target) {
      return target && target.kind === "figure" &&
        target.block_id === block.block_id && Array.isArray(target.panels) &&
        target.panels.length;
    });
    if (!candidates.length) return [];
    var panels = candidates[0].panels;
    if (candidates.some(function (target) {
      return stableStringify(target.panels) !== stableStringify(panels);
    })) {
      throw new Error("ALC reader Figure panel manifest is inconsistent");
    }
    panels.forEach(function (panel, index) {
      if (!panel || panel.panel_index !== index) {
        throw new Error("ALC reader Figure panel order is invalid");
      }
    });
    return panels;
  }

  function hydrateResource(resource) {
    if (!resource || typeof resource.data_uri === "string") return resource;
    if (!resource.payload_id) return resource;
    var node = document.getElementById(resource.payload_id);
    if (!node) throw new Error("ALC reader resource payload is missing");
    var value = JSON.parse(node.textContent || "");
    var loaded = value && value.resource;
    if (
      !loaded || value.schema_version !== "alc.render.reader_resource.v1" ||
      loaded.artifact_digest !== resource.artifact_digest ||
      typeof loaded.data_uri !== "string"
    ) {
      throw new Error("ALC reader resource payload is invalid");
    }
    Object.assign(resource, loaded);
    return resource;
  }

  function fragmentMetaText(fragment, editing) {
    var role = roleLabel(fragment.role);
    if (editing) {
      return role + " · " + fragment.priority + " · v" + fragment.revision;
    }
    return fragment.revision === 1
      ? role
      : role + " · v" + fragment.revision;
  }

  function normalizeHexColor(value) {
    var color = String(value || "");
    if (!HEX_COLOR.test(color)) throw new Error("color must use #rrggbb");
    return color.toLowerCase();
  }

  function normalizeAppearance(value) {
    if (value === null || value === undefined) return null;
    if (!plainObject(value) || Object.keys(value).sort().join(",") !==
      "background,foreground") {
      throw new Error("fragment appearance is invalid");
    }
    return {
      foreground: normalizeHexColor(value.foreground),
      background: normalizeHexColor(value.background)
    };
  }

  function effectiveAppearance(role, appearance) {
    return appearance || ROLE_APPEARANCES[role] || {
      foreground: "#20262e", background: "#ffffff"
    };
  }

  function appearanceGroupKey(role, priority) {
    return String(role) + "\u0000" + String(priority);
  }

  function appearanceDeclarationRank(fragment) {
    var provenance = fragment.provenance || {};
    return {
      scoped: provenance.appearance_scope === "role_priority" ? 1 : 0,
      explicit: fragment.appearance ? 1 : 0,
      timestamp: String(provenance.edited_at || provenance.created_at || ""),
      revision: Number(fragment.revision || 0),
      identity: String(fragment.semantic_digest || fragment.fragment_id || "")
    };
  }

  function compareAppearanceDeclarations(left, right) {
    var a = appearanceDeclarationRank(left);
    var b = appearanceDeclarationRank(right);
    var scoped = a.scoped - b.scoped;
    if (scoped) return scoped;
    if (!a.scoped) {
      var explicit = a.explicit - b.explicit;
      if (explicit) return explicit;
    }
    return a.timestamp.localeCompare(b.timestamp) ||
      a.revision - b.revision ||
      a.identity.localeCompare(b.identity);
  }

  function syncAppearanceGroups() {
    var declarations = new Map();
    state.selected.forEach(function (fragment) {
      var key = appearanceGroupKey(fragment.role, fragment.priority);
      var current = declarations.get(key);
      if (!current || compareAppearanceDeclarations(fragment, current) > 0) {
        declarations.set(key, fragment);
      }
    });
    state.appearanceGroups = new Map();
    declarations.forEach(function (fragment, key) {
      state.appearanceGroups.set(key, {
        role: fragment.role,
        priority: fragment.priority,
        appearance: normalizeAppearance(fragment.appearance)
      });
    });
    renderAppearanceGroups();
  }

  function appearanceForGroup(role, priority) {
    var entry = state.appearanceGroups.get(appearanceGroupKey(role, priority));
    if (!entry || !entry.appearance) return null;
    return JSON.parse(JSON.stringify(entry.appearance));
  }

  function renderAppearanceGroups() {
    if (
      typeof document === "undefined" || !document.head ||
      typeof document.createElement !== "function"
    ) return;
    if (!state.appearanceStyle) {
      state.appearanceStyle = element("style");
      state.appearanceStyle.id = "alc-appearance-groups";
      document.head.appendChild(state.appearanceStyle);
    }
    var rules = [];
    state.appearanceGroups.forEach(function (entry) {
      var colors = effectiveAppearance(entry.role, entry.appearance);
      rules.push(
        '.alc-fragment[data-role-slot="' + roleSlot(entry.role) + '"]' +
        '[data-priority="' + entry.priority + '"]{' +
        "--alc-fragment-foreground:" + colors.foreground + ";" +
        "--alc-fragment-background:" + colors.background + "}"
      );
    });
    state.appearanceStyle.textContent = rules.join("\n");
  }

  function applyFragmentAppearance(node, role, appearance) {
    var colors = effectiveAppearance(role, appearance);
    if (node.style && typeof node.style.setProperty === "function") {
      node.style.setProperty("--alc-fragment-foreground", colors.foreground);
      node.style.setProperty("--alc-fragment-background", colors.background);
    } else if (node.style) {
      node.style["--alc-fragment-foreground"] = colors.foreground;
      node.style["--alc-fragment-background"] = colors.background;
    }
  }

  function renderFragment(fragment) {
    var draft = state.activeDraft;
    var editing = Boolean(
      draft && draft.base && draft.base.fragment_id === fragment.fragment_id
    );
    var visual = editing ? Object.assign({}, fragment, {
      title: draft.title,
      role: draft.role,
      priority: draft.priority,
      appearance: draft.appearance
    }) : fragment;
    var card = element("aside", "alc-fragment");
    card.dataset.fragmentId = fragment.fragment_id;
    card.dataset.revision = String(fragment.revision);
    card.dataset.role = visual.role;
    card.dataset.roleSlot = String(roleSlot(visual.role));
    card.dataset.priority = String(visual.priority);
    card.lang = visual.language ||
      (state.payload.publication.reader_profile || {}).target_language ||
      document.documentElement.lang;
    if (
      fragment.fragment_id === state.primaryTitleFragmentId &&
      visual.role === "translation" && visual.priority <= 100
    ) {
      card.classList.add("alc-translated-title");
    }
    if (editing) {
      applyFragmentAppearance(card, visual.role, visual.appearance);
    }
    var header = element("header", "alc-fragment-header");
    var title = visual.title ?
      element("h4", "", plainFragmentTitle(visual.title)) : element("span");
    decorateGlossary(title, "target");
    header.appendChild(title);
    var actions = element("div", "alc-fragment-actions");
    actions.appendChild(element(
      "span", "alc-fragment-meta", fragmentMetaText(visual, editing)
    ));
    if (editing) {
      actions.classList.add("alc-inline-actions");
      appendInlineActions(actions);
    } else {
      var accessibleEdit = element(
        "button", "alc-edit-accessible", labels().editContent
      );
      accessibleEdit.type = "button";
      accessibleEdit.addEventListener("click", function () {
        beginInlineEdit(fragment);
      });
      actions.appendChild(accessibleEdit);
    }
    header.appendChild(actions);
    card.appendChild(header);
    var saved = element("div", "alc-fragment-saved-content");
    var rendered = renderMarkdown(fragment.markdown_body, fragment);
    decorateTranslationSourceNoteTokens(rendered, fragment);
    decorateOverlayEquation(rendered, fragment);
    saved.appendChild(rendered);
    saved.addEventListener("click", function (event) {
      handleSavedFragmentClick(event, fragment);
    });
    saved.addEventListener("dblclick", function (event) {
      handleSavedFragmentDoubleClick(event, fragment);
    });
    card.appendChild(saved);
    if (editing) {
      card.classList.add("is-inline-editing");
      card.appendChild(renderInlineEditor());
    } else {
      card.appendChild(renderCardActions(
        visual.role, fragmentTargetId(fragment), fragment
      ));
      setupTouchCardActions(card);
    }
    return card;
  }

  function setupTouchCardActions(card, interactiveTarget) {
    var targetIsInteractive = interactiveTarget || interactiveFragmentTarget;
    card.addEventListener("pointerdown", function (event) {
      if (!event || event.pointerType === "mouse") return;
      if (targetIsInteractive(event.target)) return;
      if (card.classList.contains("is-touch-actions-revealed")) {
        delete card.dataset.alcSuppressTouchClick;
        return;
      }
      Array.prototype.forEach.call(
        document.querySelectorAll(".is-touch-actions-revealed"),
        function (other) {
          if (other !== card) {
            other.classList.remove("is-touch-actions-revealed");
            delete other.dataset.alcSuppressTouchClick;
          }
        }
      );
      card.classList.add("is-touch-actions-revealed");
      card.dataset.alcSuppressTouchClick = "true";
    });
    card.addEventListener("click", function (event) {
      if (card.dataset.alcSuppressTouchClick !== "true") return;
      delete card.dataset.alcSuppressTouchClick;
      event.preventDefault();
      event.stopPropagation();
      if (typeof event.stopImmediatePropagation === "function") {
        event.stopImmediatePropagation();
      }
    }, true);
  }

  function renderCardActions(role, blockId, fragment) {
    var root = element("div", "alc-card-actions");
    root.setAttribute("aria-label", roleLabel(role) + " actions");
    var speech = element("button", "alc-card-action");
    speech.type = "button";
    var speechLabel = labels().listen + " · " + roleLabel(role);
    speech.setAttribute("aria-label", speechLabel);
    speech.title = speechLabel;
    speech.innerHTML = speechIcon("speaker");
    speech.addEventListener("click", function (event) {
      event.preventDefault();
      event.stopPropagation();
      playSpeechFromCard(role, blockId, fragment && fragment.fragment_id);
    });
    root.appendChild(speech);
    if (fragment) {
      var edit = element("button", "alc-card-action");
      edit.type = "button";
      edit.setAttribute("aria-label", labels().editContent);
      edit.title = labels().editContent;
      edit.innerHTML = speechIcon("edit");
      edit.addEventListener("click", function (event) {
        event.preventDefault();
        event.stopPropagation();
        beginInlineEdit(fragment);
      });
      root.appendChild(edit);
    }
    return root;
  }

  function renderClassificationActions(relation, fragments, editFragment) {
    var root = element("div", "alc-card-actions alc-classification-actions");
    root.setAttribute("aria-label", roleLabel("translation") + " actions");
    var speech = element("button", "alc-card-action");
    speech.type = "button";
    var speechLabel = labels().listen + " · " + roleLabel("translation");
    speech.setAttribute("aria-label", speechLabel);
    speech.title = speechLabel;
    speech.innerHTML = speechIcon("speaker");
    speech.addEventListener("click", function (event) {
      event.preventDefault();
      event.stopPropagation();
      playClassificationSpeech(relation, fragments);
    });
    root.appendChild(speech);
    if (editFragment) {
      var edit = element("button", "alc-card-action");
      edit.type = "button";
      edit.setAttribute("aria-label", labels().editContent);
      edit.title = labels().editContent;
      edit.innerHTML = speechIcon("edit");
      edit.addEventListener("click", function (event) {
        event.preventDefault();
        event.stopPropagation();
        beginInlineEdit(editFragment);
      });
      root.appendChild(edit);
    }
    return root;
  }

  function renderGlossaryCardActions(entry) {
    var strings = labels();
    var source = glossarySourceTerm(entry);
    var root = element("div", "alc-card-actions alc-glossary-card-actions");
    root.setAttribute("aria-label", strings.glossary + " actions");

    var speech = element("button", "alc-card-action");
    speech.type = "button";
    var speechLabel = strings.listen + " · " + source;
    speech.setAttribute("aria-label", speechLabel);
    speech.title = speechLabel;
    speech.innerHTML = speechIcon("speaker");
    speech.addEventListener("click", function (event) {
      event.preventDefault();
      event.stopPropagation();
      playGlossarySpeech(entry);
    });
    root.appendChild(speech);

    var edit = element("button", "alc-card-action");
    edit.type = "button";
    var editLabel = strings.editGlossary + ": " + source;
    edit.setAttribute("aria-label", editLabel);
    edit.title = editLabel;
    edit.innerHTML = speechIcon("edit");
    edit.addEventListener("click", function (event) {
      event.preventDefault();
      event.stopPropagation();
      beginGlossaryEdit(entry);
    });
    root.appendChild(edit);
    return root;
  }

  function decorateOverlayEquation(rendered, fragment) {
    var block = ensureSourceIndexes().blocksById.get(fragmentTargetId(fragment));
    if (!block || block.kind !== "equation") return;
    if (rendered.children.length !== 1) return;
    var math = rendered.firstElementChild;
    if (!math || !math.classList.contains("math-display")) return;
    var sourceTex = String((block.payload || {}).tex || "").replace(/\r\n?/g, "\n").trim();
    var fragmentTex = String(math.dataset.tex || "").replace(/\r\n?/g, "\n").trim();
    if (!sourceTex || fragmentTex !== sourceTex) return;
    var label = effectiveEquationLabel(block, block.payload || {});
    equationRow(math, label);
  }

  function interactiveFragmentTarget(target) {
    return Boolean(target && target.closest && target.closest(
      "a, button, input, textarea, select, .glossary-term"
    ));
  }

  function interactiveGlossaryEditTarget(target) {
    return Boolean(target && target.closest && target.closest(
      "a, button, input, textarea, select"
    ));
  }

  function handleGlossaryEntryClick(event, entry) {
    if (state.readerPreferences.editActivation !== "single") return;
    if (interactiveGlossaryEditTarget(event && event.target)) return;
    beginGlossaryEdit(entry);
  }

  function handleGlossaryEntryDoubleClick(event, entry) {
    if (state.readerPreferences.editActivation !== "double") return;
    if (interactiveGlossaryEditTarget(event && event.target)) return;
    if (event && typeof event.preventDefault === "function") {
      event.preventDefault();
    }
    if (event && typeof event.stopPropagation === "function") {
      event.stopPropagation();
    }
    var focusField = event && event.target && event.target.closest &&
      event.target.closest(".alc-glossary-translation") ?
      "translation" : "definition";
    beginGlossaryEdit(entry, focusField);
  }

  function clearPendingReaderLink() {
    if (state.pendingReaderLinkTimer !== null) {
      window.clearTimeout(state.pendingReaderLinkTimer);
      state.pendingReaderLinkTimer = null;
    }
    state.pendingReaderLinkHref = "";
  }

  function followReaderLink(href, keyboardNavigation) {
    if (!href) return;
    var url;
    try {
      url = new URL(href, window.location.href);
    } catch (_error) {
      return;
    }
    if (
      url.origin === window.location.origin &&
      url.pathname === window.location.pathname &&
      url.search === window.location.search &&
      url.hash
    ) {
      activateHashTarget(url.hash, true, keyboardNavigation === true);
      return;
    }
    window.location.assign(url.href);
  }

  function handleSavedFragmentClick(event, fragment) {
    if (state.readerPreferences.editActivation === "single") {
      if (!interactiveFragmentTarget(event.target)) beginInlineEdit(fragment);
      return;
    }
    var link = event.target && event.target.closest && event.target.closest("a[href]");
    if (!link) return;
    event.preventDefault();
    clearPendingReaderLink();
    state.pendingReaderLinkHref = link.href;
    state.pendingReaderLinkTimer = window.setTimeout(function () {
      var href = state.pendingReaderLinkHref;
      clearPendingReaderLink();
      followReaderLink(href, event.detail === 0);
    }, 260);
  }

  function handleSavedFragmentDoubleClick(event, fragment) {
    if (state.readerPreferences.editActivation !== "double") return;
    if (event.target && event.target.closest && event.target.closest(
      "button, input, textarea, select"
    )) return;
    event.preventDefault();
    event.stopPropagation();
    clearPendingReaderLink();
    beginInlineEdit(fragment);
  }

  function appendInlineActions(actions) {
    var strings = labels();
    var advanced = element("button", "alc-inline-advanced", strings.advancedAction);
    advanced.type = "button";
    advanced.addEventListener("click", openAdvancedEditor);
    var cancel = element("button", "alc-inline-cancel", strings.cancel);
    cancel.type = "button";
    cancel.addEventListener("click", cancelActiveDraft);
    var save = element("button", "alc-inline-save", strings.save);
    save.type = "button";
    save.disabled = !activeDraftHasChanges();
    save.addEventListener("click", saveEditor);
    actions.appendChild(advanced);
    actions.appendChild(cancel);
    actions.appendChild(save);
  }

  function renderInlineEditor() {
    var root = element("div", "alc-inline-editor");
    var textarea = element("textarea", "alc-inline-markdown");
    textarea.value = state.activeDraft ? state.activeDraft.markdown_body : "";
    textarea.setAttribute("aria-label", labels().markdown);
    textarea.spellcheck = true;
    textarea.addEventListener("input", function () {
      if (!state.activeDraft) return;
      state.activeDraft.markdown_body = textarea.value;
      resizeInlineTextarea(textarea);
      updateDraftSaveButtons(textarea.closest(".alc-fragment"));
    });
    textarea.addEventListener("keydown", function (event) {
      if ((event.ctrlKey || event.metaKey) && event.key === "Enter") {
        event.preventDefault();
        if (activeDraftHasChanges()) saveEditor(event);
      }
    });
    var classification = classificationValueEditorContext();
    if (classification) {
      root.classList.add("alc-classification-composite-editor");
      var prefix = element("div", "alc-classification-editor-prefix");
      prefix.id = "alc-classification-editor-prefix-" + safeToken(
        classification.relation.classification_id
      );
      prefix.appendChild(renderMarkdown(
        classification.heading.markdown_body, classification.heading
      ));
      prefix.appendChild(element(
        "span", "alc-source-classification-separator",
        classification.relation.separator
      ));
      textarea.setAttribute("aria-describedby", prefix.id);
      root.appendChild(prefix);
    }
    root.appendChild(textarea);
    window.requestAnimationFrame(function () {
      resizeInlineTextarea(textarea);
      textarea.focus();
      textarea.setSelectionRange(textarea.value.length, textarea.value.length);
    });
    return root;
  }

  function classificationValueEditorContext() {
    var draft = state.activeDraft;
    var base = draft && draft.base;
    if (!base || base.role !== "translation") return null;
    var documentValue = state.payload.publication.source_document;
    var relation = sourceClassificationForValue(
      documentValue, fragmentTargetId(base)
    );
    if (!relation) return null;
    var headings = regularTranslationFragments(relation.heading_block_id);
    if (headings.length !== 1) {
      throw new Error("source classification heading translation is ambiguous");
    }
    return {relation: relation, heading: headings[0]};
  }

  function resizeInlineTextarea(textarea) {
    textarea.style.height = "auto";
    var maximum = Math.max(160, Math.round(window.innerHeight * 0.6));
    textarea.style.height = Math.min(textarea.scrollHeight, maximum) + "px";
  }

  function roleLabel(role) {
    var strings = labels();
    return strings[role] || role;
  }

  function roleSlot(role) {
    if (!state.roleSlots.has(role)) {
      state.roleSlots.set(role, state.roleSlots.size);
    }
    return state.roleSlots.get(role);
  }

  function syncVisibilityRoles() {
    var roles = [];
    (state.payload.selected_roles || []).forEach(function (role) {
      if (roles.indexOf(role) < 0) roles.push(role);
    });
    state.roleOrder.forEach(function (role) {
      if (roles.indexOf(role) < 0) roles.push(role);
    });
    Array.from(state.selected.values()).filter(fragmentIsVisible).sort(function (left, right) {
      return left.priority - right.priority ||
        left.fragment_id.localeCompare(right.fragment_id);
    }).forEach(function (fragment) {
      if (roles.indexOf(fragment.role) < 0) roles.push(fragment.role);
    });
    var changed = roles.length !== state.roleOrder.length || roles.some(function (
      role, index
    ) {
      return state.roleOrder[index] !== role;
    });
    state.roleOrder = roles;
    roles.forEach(roleSlot);
    if (!state.visibilityReady) return;
    if (changed) {
      renderVisibilityOptions();
      if (state.speechReady) renderSpeechRoleOptions();
    }
    applyVisibility();
  }

  function setupVisibility() {
    var strings = labels();
    var control = document.querySelector(".alc-view-control");
    var trigger = document.getElementById("alc-view");
    var panel = document.getElementById("alc-view-panel");
    labelToolButton(trigger, strings.view);
    document.getElementById("alc-view-heading").textContent = strings.showLayers;
    state.visibilityReady = true;
    syncVisibilityRoles();
    renderVisibilityOptions();
    applyVisibility();
    trigger.addEventListener("click", function () {
      panel.hidden = !panel.hidden;
      trigger.setAttribute("aria-expanded", String(!panel.hidden));
      if (!panel.hidden) positionToolPanel(panel);
    });
    window.addEventListener("resize", function () { positionToolPanel(panel); });
    document.addEventListener("click", function (event) {
      if (!panel.hidden && !control.contains(event.target)) {
        closeVisibilityPanel(false);
      }
    });
    document.addEventListener("keydown", function (event) {
      if (event.key === "Escape" && !panel.hidden) {
        event.preventDefault();
        closeVisibilityPanel(true);
      }
    });
  }

  function closeVisibilityPanel(restoreFocus) {
    var trigger = document.getElementById("alc-view");
    document.getElementById("alc-view-panel").hidden = true;
    trigger.setAttribute("aria-expanded", "false");
    if (restoreFocus) trigger.focus();
  }

  function renderVisibilityOptions() {
    var root = document.getElementById("alc-view-options");
    if (!root) return;
    root.replaceChildren();
    root.appendChild(visibilityOption("source", labels().original, state.sourceVisible));
    root.appendChild(visibilityOption(
      "page-markers", labels().documentData, state.pageMarkersVisible
    ));
    state.roleOrder.forEach(function (role) {
      root.appendChild(visibilityOption(
        role, roleLabel(role), !state.hiddenRoles.has(role)
      ));
    });
  }

  function visibilityOption(value, text, checked) {
    var label = element("label");
    var input = element("input");
    input.type = "checkbox";
    input.value = value;
    input.checked = checked;
    input.addEventListener("change", function () {
      if (value === "source") {
        state.sourceVisible = input.checked;
      } else if (value === "page-markers") {
        state.pageMarkersVisible = input.checked;
      } else if (input.checked) {
        state.hiddenRoles.delete(value);
      } else {
        state.hiddenRoles.add(value);
      }
      applyVisibility();
    });
    label.appendChild(input);
    label.appendChild(element("span", "", text));
    return label;
  }

  function visibleRoleCount() {
    return state.roleOrder.filter(function (role) {
      return !state.hiddenRoles.has(role);
    }).length;
  }

  function applyVisibility(scope) {
    if (!state.visibilityReady) return;
    var channels = (state.sourceVisible ? 1 : 0) + visibleRoleCount();
    document.body.classList.toggle("alc-focused-reading", channels === 1);
    document.body.classList.toggle("alc-no-visible-content", channels === 0);
    document.body.classList.toggle("alc-source-hidden", !state.sourceVisible);
    document.body.classList.toggle(
      "alc-translation-hidden", state.hiddenRoles.has("translation")
    );
    document.body.classList.toggle(
      "alc-show-page-markers", state.pageMarkersVisible
    );
    if (state.visibilityEmptyRoot) state.visibilityEmptyRoot.hidden = channels !== 0;
    updateVisibilityStyles(channels);
    if (!scope) {
      var signature = state.sourceVisible ? "source" : Array.from(
        state.hiddenRoles
      ).sort().join("\u0000");
      if (signature !== state.visibilityContentsSignature) {
        state.visibilityContentsSignature = signature;
        updateContentsTitles();
      }
    }
    scheduleScrollableTableSync();
  }

  function updateVisibilityStyles(channels) {
    if (!state.visibilityStyle) {
      state.visibilityStyle = element("style");
      state.visibilityStyle.id = "alc-visibility-state";
      document.head.appendChild(state.visibilityStyle);
    }
    var rules = [];
    state.hiddenRoles.forEach(function (role) {
      rules.push(
        '.alc-fragment[data-role-slot="' + roleSlot(role) + '"]{display:none}'
      );
    });
    if (!state.sourceVisible) {
      rules.push(".alc-source-card{display:none}");
      var translationSlot = state.roleSlots.get("translation");
      var translationVisible = translationSlot !== undefined &&
        !state.hiddenRoles.has("translation");
      if (channels > 0 && !translationVisible) {
        rules.push(
          '.alc-source-row[data-block-kind="figure"] .alc-source-card{display:block}'
        );
      }
      var visibleSlots = state.roleOrder.filter(function (role) {
        return !state.hiddenRoles.has(role);
      }).map(function (role) {
        return '.alc-fragment[data-role-slot="' + roleSlot(role) + '"]';
      });
      if (visibleSlots.length) {
        rules.push(
          '.alc-source-row:not([data-block-kind="figure"]):not(:has(' +
          visibleSlots.join(",") + ")){display:none}"
        );
      } else {
        rules.push(
          '.alc-source-row:not([data-block-kind="figure"]){display:none}'
        );
      }
      if (
        translationVisible
      ) {
        rules.push(
          '.alc-source-row[data-block-kind="figure"]:has(' +
          '.alc-fragment[data-role-slot="' + translationSlot + '"]) ' +
          ".alc-source-card figcaption{display:none}"
        );
      }
    }
    state.visibilityStyle.textContent = rules.join("\n");
  }

  function speechIcon(name) {
    var paths = {
      playlist: '<path d="M9 6h11M9 12h11M9 18h11"></path>' +
        '<circle cx="4" cy="6" r="1"></circle><circle cx="4" cy="12" r="1"></circle>' +
        '<circle cx="4" cy="18" r="1"></circle>',
      previous: '<path d="M18 5 8 12l10 7Z"></path><path d="M6 5v14"></path>',
      play: '<path class="is-solid" d="m8 5 11 7-11 7Z"></path>',
      pause: '<path class="is-solid" d="M7 5h4v14H7zM13 5h4v14h-4z"></path>',
      next: '<path d="m6 5 10 7-10 7Z"></path><path d="M18 5v14"></path>',
      beginning: '<path d="M6 5v14"></path><path class="is-solid" d="m18 5-10 7 10 7Z"></path>',
      stop: '<rect class="is-solid" x="6" y="6" width="12" height="12" rx="1"></rect>',
      loopNone: '<path d="M3 7h15"></path><path d="m14 3 4 4-4 4"></path>' +
        '<path d="M3 17h15"></path><path d="m14 13 4 4-4 4"></path>',
      loopAll: '<path d="m17 2 4 4-4 4"></path><path d="M3 11V9a3 3 0 0 1 3-3h14"></path>' +
        '<path d="m7 22-4-4 4-4"></path><path d="M21 13v2a3 3 0 0 1-3 3H4"></path>',
      loopOne: '<path d="m17 2 4 4-4 4"></path><path d="M3 11V9a3 3 0 0 1 3-3h14"></path>' +
        '<path d="m7 22-4-4 4-4"></path><path d="M21 13v2a3 3 0 0 1-3 3H4"></path>' +
        '<path d="M11 10.5 13 9v6"></path>',
      speaker: '<path d="M11 5 6 9H2v6h4l5 4V5Z"></path>' +
        '<path d="M15.54 8.46a5 5 0 0 1 0 7.07M19.07 4.93a10 10 0 0 1 0 14.14"></path>',
      edit: '<path d="m4 20 4.2-1 10.6-10.6-3.2-3.2L5 15.8 4 20Z"></path>' +
        '<path d="m13.8 7 3.2 3.2"></path>',
      close: '<path d="M6 6l12 12M18 6 6 18"></path>'
    };
    return '<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">' +
      (paths[name] || "") + "</svg>";
  }

  function speechPlayerButton(action, icon, label, className) {
    var button = element("button", "alc-speech-player-button " + (className || ""));
    button.type = "button";
    button.dataset.speechAction = action;
    button.setAttribute("aria-label", label);
    button.title = label;
    button.innerHTML = speechIcon(icon);
    return button;
  }

  function renderSpeechPlayer(root) {
    var strings = labels();
    var copy = element("div", "alc-speech-player-copy");
    copy.appendChild(element("span", "alc-speech-player-progress", ""));
    copy.appendChild(element("strong", "alc-speech-player-title", ""));
    var transport = element("div", "alc-speech-player-transport");
    transport.appendChild(speechPlayerButton(
      "playlist", "playlist", strings.speechPlaylist
    ));
    transport.appendChild(speechPlayerButton(
      "previous", "previous", strings.speechPrevious
    ));
    transport.appendChild(speechPlayerButton(
      "play", "play", strings.speechPlay, "is-primary"
    ));
    transport.appendChild(speechPlayerButton(
      "next", "next", strings.speechNext
    ));
    transport.appendChild(speechPlayerButton(
      "beginning", "beginning", strings.speechFromBeginning
    ));
    transport.appendChild(speechPlayerButton(
      "stop", "stop", strings.speechStop
    ));
    transport.appendChild(speechPlayerButton(
      "loop", "loopNone", strings.speechLoopNone
    ));
    var rate = element("button", "alc-speech-rate-trigger", "");
    rate.type = "button";
    rate.dataset.speechAction = "rate";
    rate.setAttribute("aria-haspopup", "listbox");
    rate.setAttribute("aria-expanded", "false");
    transport.appendChild(rate);
    if (root.dataset.playerKind === "dock") {
      transport.appendChild(speechPlayerButton(
        "close", "close", strings.close
      ));
    }
    var rateMenu = element("div", "alc-speech-rate-menu");
    rateMenu.hidden = true;
    rateMenu.setAttribute("role", "listbox");
    [0.5, 0.8, 1, 1.2, 1.5, 2, 2.5, 3].forEach(function (value) {
      var option = element("button", "alc-speech-rate-option", value + "×");
      option.type = "button";
      option.dataset.speechRate = String(value);
      option.setAttribute("role", "option");
      option.addEventListener("click", function (event) {
        event.stopPropagation();
        setSpeechRate(value);
        closeSpeechRateMenus();
      });
      rateMenu.appendChild(option);
    });
    var playlist = element("section", "alc-speech-playlist");
    playlist.hidden = true;
    playlist.innerHTML =
      '<header><h2></h2><button type="button" data-speech-action="playlist-close" ' +
        'aria-label="' + strings.close + '">' + speechIcon("close") + '</button></header>' +
      '<ol></ol>';
    root.replaceChildren(copy, transport, rateMenu, playlist);
    root.addEventListener("click", handleSpeechPlayerAction);
    syncSpeechPlayers();
  }

  function speechPlayers() {
    if (!document.querySelectorAll) return [];
    return Array.prototype.slice.call(
      document.querySelectorAll(".alc-speech-player")
    );
  }

  function speechCurrentSegment() {
    return state.speechIndex >= 0 ? state.speechQueue[state.speechIndex] : null;
  }

  function speechSegmentLabel(segment) {
    if (!segment) return labels().speechChooseContent;
    return normalizeSpeechText(speechSegmentText(segment)).slice(0, 120);
  }

  function loopLabel() {
    if (state.speechLoopMode === "one") return labels().speechLoopOne;
    if (state.speechLoopMode === "all") return labels().speechLoopAll;
    return labels().speechLoopNone;
  }

  function loopIconName() {
    if (state.speechLoopMode === "one") return "loopOne";
    if (state.speechLoopMode === "all") return "loopAll";
    return "loopNone";
  }

  function syncSpeechPlayers() {
    if (typeof document === "undefined") return;
    var playable = state.speechSupported && state.speechVoices.length > 0 &&
      state.speechRoles.size > 0;
    var segment = speechCurrentSegment();
    speechPlayers().forEach(function (player) {
      var progress = player.querySelector(".alc-speech-player-progress");
      var title = player.querySelector(".alc-speech-player-title");
      if (progress) {
        var showProgress = state.speechPlaying && state.speechQueue.length &&
          state.speechIndex >= 0;
        progress.textContent = showProgress ?
          speechProgressText(state.speechIndex, state.speechQueue.length) :
          state.speechStatus;
        progress.dataset.kind = !showProgress && state.speechStatusError ?
          "error" : "info";
      }
      if (title) title.textContent = speechSegmentLabel(segment);
      var play = player.querySelector('[data-speech-action="play"]');
      if (play) {
        var pausing = state.speechPlaying && !state.speechPaused;
        play.innerHTML = speechIcon(pausing ? "pause" : "play");
        play.setAttribute(
          "aria-label", pausing ? labels().speechPause :
            state.speechPaused ? labels().speechResume : labels().speechPlay
        );
        play.title = play.getAttribute("aria-label");
        play.disabled = !playable;
      }
      var previous = player.querySelector('[data-speech-action="previous"]');
      var next = player.querySelector('[data-speech-action="next"]');
      var beginning = player.querySelector('[data-speech-action="beginning"]');
      var stop = player.querySelector('[data-speech-action="stop"]');
      var playlist = player.querySelector('[data-speech-action="playlist"]');
      if (previous) previous.disabled = !state.speechPlaying || state.speechIndex <= 0;
      if (next) next.disabled = !state.speechPlaying ||
        state.speechIndex >= state.speechQueue.length - 1;
      if (beginning) beginning.disabled = !playable;
      if (stop) stop.disabled = !state.speechPlaying;
      if (playlist) playlist.disabled = !state.speechRoles.size;
      var loop = player.querySelector('[data-speech-action="loop"]');
      if (loop) {
        loop.innerHTML = speechIcon(loopIconName());
        loop.setAttribute("aria-label", loopLabel());
        loop.title = loopLabel();
        loop.setAttribute(
          "aria-pressed", String(state.speechLoopMode !== "none")
        );
        loop.disabled = !playable;
      }
      var rate = player.querySelector('[data-speech-action="rate"]');
      if (rate) {
        rate.textContent = labels().speechRate + " " + state.speechRate + "×";
        rate.setAttribute(
          "aria-label", labels().speechRate + " " + state.speechRate + "×"
        );
      }
      var rateMenu = player.querySelector(".alc-speech-rate-menu");
      if (rateMenu && !rateMenu.hidden) positionSpeechRateMenu(player);
      player.querySelectorAll(".alc-speech-rate-option").forEach(function (option) {
        option.setAttribute(
          "aria-selected", String(Number(option.dataset.speechRate) === state.speechRate)
        );
      });
      var list = player.querySelector(".alc-speech-playlist");
      if (list && !list.hidden) renderSpeechPlaylist(player);
    });
  }

  function closeSpeechRateMenus() {
    speechPlayers().forEach(function (player) {
      var menu = player.querySelector(".alc-speech-rate-menu");
      var trigger = player.querySelector('[data-speech-action="rate"]');
      if (menu) menu.hidden = true;
      if (trigger) trigger.setAttribute("aria-expanded", "false");
    });
  }

  function positionSpeechRateMenu(player) {
    var menu = player.querySelector(".alc-speech-rate-menu");
    var trigger = player.querySelector('[data-speech-action="rate"]');
    if (!menu || !trigger) return;
    var playerRect = player.getBoundingClientRect();
    var triggerRect = trigger.getBoundingClientRect();
    var gutter = 8;
    var spacing = 5;
    var viewportHeight = document.documentElement.clientHeight;
    var spaceAbove = triggerRect.top - gutter;
    var spaceBelow = viewportHeight - triggerRect.bottom - gutter;
    var docked = player.dataset.playerKind === "dock";
    menu.dataset.layout = "list";
    menu.style.width = triggerRect.width + "px";
    var menuRect = menu.getBoundingClientRect();
    var grid = docked && spaceAbove < menuRect.height + spacing;
    if (grid) {
      menu.dataset.layout = "grid";
      menu.style.width = Math.max(112, triggerRect.width * 2) + "px";
    }
    var opensAbove = docked || spaceAbove >= menuRect.height + spacing ||
      spaceAbove >= spaceBelow;
    var available = opensAbove ? spaceAbove : spaceBelow;
    menu.style.right = Math.max(0, playerRect.right - triggerRect.right) + "px";
    menu.style.maxHeight = docked ? "none" : Math.max(
      112, Math.min(240, available - spacing)
    ) + "px";
    if (opensAbove) {
      menu.style.top = "auto";
      menu.style.bottom = playerRect.bottom - triggerRect.top + spacing + "px";
    } else {
      menu.style.top = triggerRect.bottom - playerRect.top + spacing + "px";
      menu.style.bottom = "auto";
    }
  }

  function toggleSpeechRateMenu(player) {
    var menu = player.querySelector(".alc-speech-rate-menu");
    var trigger = player.querySelector('[data-speech-action="rate"]');
    var opening = menu.hidden;
    closeSpeechRateMenus();
    menu.hidden = !opening;
    trigger.setAttribute("aria-expanded", String(opening));
    if (opening) positionSpeechRateMenu(player);
  }

  function setSpeechRate(value) {
    var next = Number(value);
    if (!Number.isFinite(next) || next < 0.5 || next > 3) return;
    state.speechRate = next;
    if (state.speechPlaying && state.speechIndex >= 0) {
      var paused = state.speechPaused;
      speakSpeechIndex(state.speechIndex);
      if (paused) {
        window.speechSynthesis.pause();
        state.speechPaused = true;
      }
    }
    syncSpeechPlayers();
  }

  function cycleSpeechLoop() {
    state.speechLoopMode = state.speechLoopMode === "none" ? "all" :
      state.speechLoopMode === "all" ? "one" : "none";
    syncSpeechPlayers();
  }

  function rolePlaylistLabel(role) {
    return role === "source" ? labels().original : roleLabel(role);
  }

  function updateSpeechPlaylistSelection(root) {
    var previous = Number.isInteger(root._alcSpeechCurrentIndex) ?
      root._alcSpeechCurrentIndex : -1;
    var current = state.speechPlaying ? state.speechIndex : -1;
    if (previous === current) return;
    [previous, current].forEach(function (index) {
      if (index < 0) return;
      var button = root.querySelector(
        '.alc-speech-playlist-item[data-speech-index="' + index + '"]'
      );
      if (button) button.setAttribute(
        "aria-current", String(index === current)
      );
    });
    root._alcSpeechCurrentIndex = current;
  }

  function renderSpeechPlaylist(player) {
    var root = player.querySelector(".alc-speech-playlist");
    if (!root) return;
    var queue = state.speechPlaying && state.speechQueue.length ?
      state.speechQueue : buildSpeechQueue();
    var heading = root.querySelector("h2");
    var list = root.querySelector("ol");
    heading.textContent = labels().speechPlaylist + " · " + queue.length + " " +
      (document.documentElement.lang.toLowerCase().indexOf("zh") === 0 ? "个段落" : "paragraphs");
    if (root._alcSpeechQueue === queue) {
      updateSpeechPlaylistSelection(root);
      return;
    }
    root._alcSpeechQueue = queue;
    root._alcSpeechCurrentIndex = state.speechPlaying ? state.speechIndex : -1;
    list.replaceChildren();
    var items = document.createDocumentFragment();
    queue.forEach(function (segment, index) {
      var item = element("li");
      var button = element("button", "alc-speech-playlist-item");
      button.type = "button";
      button.dataset.speechIndex = String(index);
      button.setAttribute(
        "aria-current", String(state.speechPlaying && index === state.speechIndex)
      );
      button.innerHTML =
        '<span class="alc-speech-playlist-number">' + (index + 1) + '</span>' +
        '<span class="alc-speech-playlist-role"></span>' +
        '<span class="alc-speech-playlist-text"></span>';
      button.querySelector(".alc-speech-playlist-role").textContent =
        rolePlaylistLabel(segment.role);
      button.querySelector(".alc-speech-playlist-text").textContent =
        speechSegmentLabel(segment);
      button.addEventListener("click", function () {
        if (!speechSegmentText(queue[index])) {
          setSpeechStatus(labels().speechNoReadableContent, true);
          return;
        }
        state.speechQueue = queue;
        speakSpeechIndex(index);
        root.hidden = true;
        syncSpeechPlayers();
      });
      item.appendChild(button);
      items.appendChild(item);
    });
    list.appendChild(items);
  }

  function toggleSpeechPlaylist(player) {
    var root = player.querySelector(".alc-speech-playlist");
    var opening = root.hidden;
    speechPlayers().forEach(function (candidate) {
      var playlist = candidate.querySelector(".alc-speech-playlist");
      if (playlist) playlist.hidden = true;
    });
    root.hidden = !opening;
    if (opening) renderSpeechPlaylist(player);
  }

  function playSpeechFromBeginning() {
    if (!state.speechQueue.length) state.speechQueue = buildSpeechQueue();
    if (!state.speechQueue.length) {
      setSpeechStatus(labels().speechNoReadableContent, true);
      return;
    }
    speakSpeechIndex(0);
  }

  function handleSpeechPlayerAction(event) {
    var button = event.target.closest && event.target.closest("[data-speech-action]");
    if (!button) return;
    event.preventDefault();
    event.stopPropagation();
    var player = button.closest(".alc-speech-player");
    var action = button.dataset.speechAction;
    if (action === "playlist") toggleSpeechPlaylist(player);
    else if (action === "playlist-close") {
      player.querySelector(".alc-speech-playlist").hidden = true;
    } else if (action === "previous") moveSpeech(-1);
    else if (action === "play") {
      if (state.speechPlaying) toggleSpeechPause();
      else playSpeech();
    } else if (action === "next") moveSpeech(1);
    else if (action === "beginning") playSpeechFromBeginning();
    else if (action === "stop") stopSpeech(true);
    else if (action === "loop") cycleSpeechLoop();
    else if (action === "rate") toggleSpeechRateMenu(player);
    else if (action === "close") {
      stopSpeech(false);
      document.getElementById("alc-speech-dock").hidden = true;
      document.body.classList.remove("alc-speech-dock-open");
    }
    syncSpeechPlayers();
  }

  function setupSpeech() {
    var strings = labels();
    var control = document.querySelector(".alc-speech-control");
    var trigger = document.getElementById("alc-speech");
    var panel = document.getElementById("alc-speech-panel");
    labelToolButton(trigger, strings.listen);
    document.getElementById("alc-speech-heading").textContent =
      strings.readContent;
    document.getElementById("alc-speech-content-label").textContent =
      strings.markdownContent;
    document.getElementById("alc-speech-source-voice-label").textContent =
      strings.sourceVoice;
    document.getElementById("alc-speech-target-voice-label").textContent =
      strings.targetVoice;
    renderSpeechPlayer(document.getElementById("alc-speech-panel-player"));
    renderSpeechPlayer(document.getElementById("alc-speech-dock"));
    state.speechSupported = Boolean(
      window.speechSynthesis &&
      typeof window.SpeechSynthesisUtterance === "function"
    );
    state.speechReady = true;
    renderSpeechRoleOptions();

    trigger.addEventListener("click", function () {
      panel.hidden = !panel.hidden;
      trigger.setAttribute("aria-expanded", String(!panel.hidden));
      if (!panel.hidden) {
        positionToolPanel(panel);
        refreshSpeechVoices();
      }
    });
    window.addEventListener("resize", function () { positionToolPanel(panel); });
    ["source", "target"].forEach(function (kind) {
      var select = document.getElementById("alc-speech-" + kind + "-voice");
      select.addEventListener("change", function () {
        state.speechVoiceIdentities[kind] = select.value;
      });
      installCustomSelect(select);
    });
    document.addEventListener("click", function (event) {
      var inListbox = event.target.closest && event.target.closest(
        ".alc-select-listbox, .alc-speech-rate-menu"
      );
      if (!panel.hidden && !control.contains(event.target) && !inListbox) {
        closeSpeechPanel(false);
      }
      if (!event.target.closest || !event.target.closest(
        ".alc-speech-rate-trigger, .alc-speech-rate-menu"
      )) closeSpeechRateMenus();
    });
    document.addEventListener("keydown", function (event) {
      if (event.key === "Escape" && !panel.hidden) {
        event.preventDefault();
        closeSpeechPanel(true);
      }
    });

    if (!state.speechSupported) {
      renderSpeechVoiceOptions();
      setSpeechStatus(strings.speechUnavailable, true);
      updateSpeechControls();
      return;
    }
    if (typeof window.speechSynthesis.addEventListener === "function") {
      window.speechSynthesis.addEventListener(
        "voiceschanged", refreshSpeechVoices
      );
    } else {
      window.speechSynthesis.onvoiceschanged = refreshSpeechVoices;
    }
    window.addEventListener("beforeunload", function () { stopSpeech(false); });
    refreshSpeechVoices();
  }

  function closeSpeechPanel(restoreFocus) {
    var trigger = document.getElementById("alc-speech");
    document.getElementById("alc-speech-panel").hidden = true;
    trigger.setAttribute("aria-expanded", "false");
    if (restoreFocus) trigger.focus();
  }

  function renderSpeechRoleOptions() {
    var root = document.getElementById("alc-speech-role-options");
    if (!root) return;
    root.replaceChildren();
    root.appendChild(speechRoleOption("source", labels().original));
    state.roleOrder.forEach(function (role) {
      root.appendChild(speechRoleOption(role, roleLabel(role)));
    });
    updateSpeechControls();
  }

  function speechRoleOption(role, text) {
    var label = element("label");
    var input = element("input");
    input.type = "checkbox";
    input.value = role;
    input.checked = state.speechRoles.has(role);
    input.addEventListener("change", function () {
      if (input.checked) state.speechRoles.add(role);
      else state.speechRoles.delete(role);
      if (state.speechPlaying) stopSpeech(false);
      if (!state.speechRoles.size) {
        setSpeechStatus(labels().speechChooseContent, true);
      } else if (state.speechSupported && state.speechVoices.length) {
        setSpeechStatus(labels().speechReady, false);
      }
      updateSpeechControls();
    });
    label.appendChild(input);
    label.appendChild(element("span", "", text));
    return label;
  }

  function refreshSpeechVoices() {
    if (!state.speechSupported) return;
    var voices = [];
    try {
      voices = Array.prototype.slice.call(window.speechSynthesis.getVoices() || []);
    } catch (_error) {
      voices = [];
    }
    voices.sort(function (left, right) {
      return String(left.lang || "").localeCompare(String(right.lang || "")) ||
        String(left.name || "").localeCompare(String(right.name || ""));
    });
    state.speechVoices = voices;
    ["source", "target"].forEach(function (kind) {
      var identity = state.speechVoiceIdentities[kind];
      if (identity && !voices.some(function (voice) {
        return speechVoiceIdentity(voice) === identity;
      })) state.speechVoiceIdentities[kind] = "";
    });
    renderSpeechVoiceOptions();
    if (!voices.length) {
      setSpeechStatus(labels().speechNoVoices, true);
    } else if (!state.speechPlaying) {
      setSpeechStatus(
        state.speechRoles.size ? labels().speechReady : labels().speechChooseContent,
        !state.speechRoles.size
      );
    }
    updateSpeechControls();
  }

  function speechVoiceIdentity(voice) {
    return JSON.stringify([
      String(voice.voiceURI || ""),
      String(voice.name || ""),
      String(voice.lang || "")
    ]);
  }

  function speechVoiceDescription(voice) {
    if (!voice) return "";
    var service = voice.localService === true ? labels().localVoice :
      voice.localService === false ? labels().networkVoice : "";
    return [
      voice.name || voice.voiceURI || labels().voice,
      voice.lang || "",
      service
    ].filter(Boolean).join(" · ");
  }

  function primaryLanguageTag(value) {
    return String(value || "").toLowerCase().split("-")[0];
  }

  function speechProfileLanguage(kind) {
    var profile = state.payload.publication.reader_profile || {};
    return kind === "source" ? profile.source_language || "" :
      profile.target_language || profile.source_language || "";
  }

  function voiceMatchesLanguage(voice, language) {
    var expected = primaryLanguageTag(language);
    if (!expected) return true;
    return primaryLanguageTag(voice && voice.lang) === expected;
  }

  function renderSpeechVoiceOptions() {
    ["source", "target"].forEach(function (kind) {
      var select = document.getElementById("alc-speech-" + kind + "-voice");
      if (!select) return;
      select.replaceChildren();
      var automaticDescription = speechVoiceDescription(
        automaticSpeechVoice(speechProfileLanguage(kind))
      );
      var automaticLabel = automaticDescription ?
        labels().automaticVoiceSelection.replace(
          "{voice}", automaticDescription
        ) : labels().automaticVoice;
      var automatic = element("option", "", automaticLabel);
      automatic.value = "";
      select.appendChild(automatic);
      var matching = state.speechVoices.filter(function (voice) {
        return voiceMatchesLanguage(voice, speechProfileLanguage(kind));
      });
      matching.forEach(function (voice) {
        var option = element("option", "", speechVoiceDescription(voice));
        option.value = speechVoiceIdentity(voice);
        select.appendChild(option);
      });
      select.value = state.speechVoiceIdentities[kind] || "";
      select.disabled = !state.speechSupported || !matching.length;
      syncCustomSelect(select);
    });
  }

  function normalizeSpeechText(value) {
    return String(value || "").normalize("NFC")
      .replace(/[\t\f\v ]+/g, " ")
      .replace(/ *\n+ */g, "\n")
      .replace(/ +([,.;:!?，。；：！？])/g, "$1")
      .trim();
  }

  function speechInlineText(spans, fallback) {
    if (!Array.isArray(spans) || !spans.length) {
      return normalizeSpeechText(fallback);
    }
    return normalizeSpeechText(spans.map(function (span) {
      if (!span || span.kind === "math") return "";
      return span.text || "";
    }).join(""));
  }

  function speechTextFromNode(root) {
    if (!root) return "";
    var clone = root.cloneNode(true);
    Array.prototype.forEach.call(clone.querySelectorAll("table"), function (table) {
      var caption = table.querySelector("caption");
      if (!caption) {
        table.remove();
        return;
      }
      var replacement = element("p", "", caption.textContent);
      table.replaceWith(replacement);
    });
    Array.prototype.forEach.call(clone.querySelectorAll(
      "script, style, button, input, select, textarea, pre, code, .math, .katex"
    ), function (node) { node.remove(); });
    Array.prototype.forEach.call(clone.querySelectorAll("img[alt]"), function (image) {
      image.replaceWith(document.createTextNode(" " + image.alt + " "));
    });
    var selector = "h1, h2, h3, h4, h5, h6, p, li, figcaption, caption, dt, dd";
    var parts = [];
    Array.prototype.forEach.call(clone.querySelectorAll(selector), function (node) {
      var ancestor = node.parentElement;
      while (ancestor && ancestor !== clone) {
        if (ancestor.matches(selector)) return;
        ancestor = ancestor.parentElement;
      }
      var text = normalizeSpeechText(node.textContent);
      if (text) parts.push(text);
    });
    return normalizeSpeechText(parts.length ? parts.join("\n") : clone.textContent);
  }

  function sourceSpeechText(block, card) {
    var payload = (block && block.payload) || {};
    if (!block) return "";
    if (block.kind === "heading") return normalizeSpeechText(payload.text);
    if (block.kind === "paragraph") {
      return speechInlineText(payload.inline_spans, payload.text);
    }
    if (block.kind === "list") {
      return normalizeSpeechText((payload.items || []).map(function (item) {
        return typeof item === "string" ? item :
          speechInlineText(item.inline_spans, item.text);
      }).join("\n"));
    }
    if (block.kind === "figure") {
      return normalizeSpeechText(payload.caption || payload.alt_text);
    }
    if (block.kind === "table") {
      return normalizeSpeechText(payload.caption);
    }
    if (block.kind === "code" || block.kind === "equation") return "";
    return speechTextFromNode(card);
  }

  function fragmentSpeechText(fragment) {
    var content = renderMarkdown(fragment.markdown_body, fragment);
    return normalizeSpeechText([
      plainFragmentTitle(fragment.title),
      speechTextFromNode(content)
    ].filter(Boolean).join("\n"));
  }

  function plainFragmentTitle(value) {
    return String(value || "")
      .replace(/(?<!\\)\$(?!\$)([^$\n]+?)(?<!\\)\$(?!\$)/g, "$1")
      .replace(/\\\((.+?)\\\)/g, "$1")
      .replace(/\s+/g, " ")
      .trim();
  }

  function glossarySpeechText(entry) {
    var translated = String(
      entry.translated_term || entry.translation || glossarySourceTerm(entry)
    ).trim();
    return normalizeSpeechText([
      translated,
      glossaryDefinitionPlainText(entry.definition || "")
    ].filter(Boolean).join("\n"));
  }

  function buildGlossarySpeechQueue(entry) {
    var entryId = glossaryEntryId(entry);
    var source = normalizeSpeechText(glossarySourceTerm(entry));
    var target = glossarySpeechText(entry);
    var queue = [];
    if (source) {
      queue.push({
        text: source,
        role: "source",
        language: speechLanguage("source", null),
        blockId: null,
        blockIndex: -1,
        fragmentId: null,
        glossaryEntryId: entryId
      });
    }
    if (target) {
      queue.push({
        text: target,
        role: "glossary",
        language: speechLanguage("translation", null),
        blockId: null,
        blockIndex: -1,
        fragmentId: null,
        glossaryEntryId: entryId
      });
    }
    return queue;
  }

  function speechLanguage(role, revision) {
    var profile = state.payload.publication.reader_profile || {};
    if (revision && normalizedNonblank(revision.language)) {
      return revision.language;
    }
    return role === "source" ?
      profile.source_language || "" :
      profile.target_language || profile.source_language || "";
  }

  function buildSpeechQueue(selectedRoles) {
    loadAllPayload(false);
    var roles = selectedRoles || state.speechRoles;
    var queue = [];
    var blocks = state.payload.publication.source_document.blocks || [];
    blocks.forEach(function (block, blockIndex) {
      if (isPdfPageMarkerBlock(block) || isStandaloneHtmlCommentBlock(block)) {
        return;
      }
      if (roles.has("source")) {
        var sourceText = sourceSpeechText(block, null);
        if (sourceText) queue.push({
          text: sourceText,
          role: "source",
          language: speechLanguage("source", null),
          blockId: block.block_id,
          blockIndex: blockIndex,
          fragmentId: null
        });
      }
      (state.fragmentGroups.get(block.block_id) || []).forEach(function (fragment) {
        if (!fragmentIsVisible(fragment) || !roles.has(fragment.role)) return;
        queue.push({
          text: null,
          fragment: fragment,
          role: fragment.role,
          language: speechLanguage(fragment.role, fragment),
          blockId: block.block_id,
          blockIndex: blockIndex,
          fragmentId: fragment.fragment_id
        });
      });
    });
    return queue;
  }

  function playSpeechFromCard(role, blockId, fragmentId) {
    if (!state.speechSupported) {
      setSpeechStatus(labels().speechUnavailable, true);
      return;
    }
    refreshSpeechVoices();
    if (!state.speechVoices.length) return;
    var queue = buildSpeechQueue(new Set([role]));
    var index = queue.findIndex(function (segment) {
      return segment.blockId === blockId &&
        (!fragmentId || segment.fragmentId === fragmentId);
    });
    if (index < 0) {
      setSpeechStatus(labels().speechNoReadableContent, true);
      return;
    }
    if (!speechSegmentText(queue[index])) {
      setSpeechStatus(labels().speechNoReadableContent, true);
      return;
    }
    state.speechQueue = queue;
    speakSpeechIndex(index);
  }

  function playClassificationSpeech(relation, fragments) {
    if (!state.speechSupported) {
      setSpeechStatus(labels().speechUnavailable, true);
      return;
    }
    refreshSpeechVoices();
    if (!state.speechVoices.length) return;
    var parts = fragments.map(fragmentSpeechText).filter(Boolean);
    if (!parts.length) {
      setSpeechStatus(labels().speechNoReadableContent, true);
      return;
    }
    state.speechQueue = [{
      text: parts[0] + (parts.length > 1 ?
        relation.separator + parts.slice(1).join(" ") : ""),
      role: "translation",
      language: speechLanguage("translation", fragments[0]),
      blockId: relation.heading_block_id,
      fragmentId: fragments[0].fragment_id,
      classificationId: relation.classification_id
    }];
    speakSpeechIndex(0);
  }

  function playGlossarySpeech(entry) {
    if (!state.speechSupported) {
      setSpeechStatus(labels().speechUnavailable, true);
      return;
    }
    refreshSpeechVoices();
    if (!state.speechVoices.length) return;
    var queue = buildGlossarySpeechQueue(entry);
    if (!queue.length) {
      setSpeechStatus(labels().speechNoReadableContent, true);
      return;
    }
    state.speechQueue = queue;
    speakSpeechIndex(0);
  }

  function speechSegmentText(segment) {
    if (segment.text !== null && segment.text !== undefined) return segment.text;
    segment.text = fragmentSpeechText(segment.fragment);
    return segment.text;
  }

  function speechSegmentNode(segment) {
    if (segment.classificationId) {
      var classification = document.querySelector(
        '[data-source-classification-id="' +
        cssString(segment.classificationId) + '"]'
      );
      return classification && classification.querySelector(
        ".alc-source-classification-target"
      );
    }
    if (segment.glossaryEntryId) {
      return document.querySelector(
        '.alc-glossary-row[data-glossary-entry-id="' +
        cssString(segment.glossaryEntryId) + '"]'
      );
    }
    if (segment.blockId === state.primaryTitleBlockId) {
      var header = document.getElementById("alc-book-header");
      if (header && segment.role === "source") {
        return header.querySelector(":scope > h1");
      }
      if (
        header && segment.fragmentId === state.primaryTitleFragmentId
      ) {
        return header.querySelector(":scope > .alc-translated-title");
      }
    }
    var chunk = state.chunkByTargetId.get(
      "block-" + safeToken(segment.blockId)
    );
    if (chunk) renderChunk(chunk);
    var row = document.getElementById("block-" + safeToken(segment.blockId));
    if (!row) return null;
    if (segment.role === "source") return row.querySelector(".alc-source-card");
    return row.querySelector(
      '.alc-fragment[data-fragment-id="' + cssString(segment.fragmentId) + '"]'
    );
  }

  function automaticSpeechVoice(language) {
    var normalized = String(language || "").toLowerCase();
    var primary = primaryLanguageTag(normalized);
    var scored = state.speechVoices.map(function (voice, index) {
      var tag = String(voice.lang || "").toLowerCase();
      var score = 0;
      if (tag === normalized && normalized) score += 100;
      else if (primary && primaryLanguageTag(tag) === primary) score += 60;
      else if (primary) return {voice: voice, score: 0, index: index};
      else score += 1;
      if (voice.localService === true) score += 8;
      if (voice.default === true) score += 4;
      return {voice: voice, score: score, index: index};
    }).filter(function (item) { return item.score > 0; });
    scored.sort(function (left, right) {
      return right.score - left.score || left.index - right.index;
    });
    return scored.length ? scored[0].voice : null;
  }

  function selectedSpeechVoice(segment) {
    var kind = segment && segment.role === "source" ? "source" : "target";
    var identity = state.speechVoiceIdentities[kind] ||
      (kind === "source" ? state.speechVoiceIdentity : "");
    if (identity) {
      var selected = state.speechVoices.find(function (voice) {
        return speechVoiceIdentity(voice) === identity;
      });
      if (selected) return selected;
    }
    return automaticSpeechVoice(segment && segment.language);
  }

  function playSpeech() {
    if (!state.speechSupported) {
      setSpeechStatus(labels().speechUnavailable, true);
      return;
    }
    refreshSpeechVoices();
    if (!state.speechVoices.length) return;
    if (!state.speechRoles.size) {
      setSpeechStatus(labels().speechChooseContent, true);
      return;
    }
    state.speechQueue = buildSpeechQueue();
    if (!state.speechQueue.length) {
      setSpeechStatus(labels().speechNoReadableContent, true);
      updateSpeechControls();
      return;
    }
    speakSpeechIndex(speechStartIndex(state.speechQueue));
  }

  function speechStartIndex(queue) {
    var blockIndex = speechViewportBlockIndex();
    var index = queue.findIndex(function (segment) {
      return segment.blockIndex >= blockIndex;
    });
    if (index >= 0) return index;
    if (!queue.length) return 0;
    var lastBlockIndex = queue[queue.length - 1].blockIndex;
    return queue.findIndex(function (segment) {
      return segment.blockIndex === lastBlockIndex;
    });
  }

  function speechViewportBlockIndex() {
    var chunks = Array.prototype.slice.call(
      document.querySelectorAll(".alc-render-chunk")
    );
    var chunkNode = chunks[viewportNodeIndex(chunks)] || null;
    if (chunkNode) {
      var chunk = state.renderPlan.find(function (item) {
        return item.chunk_id === chunkNode.dataset.chunkId;
      });
      if (chunk && chunk.kind === "content") renderChunk(chunk);
    }
    var rows = Array.prototype.slice.call(
      document.querySelectorAll(".alc-source-row")
    );
    var row = rows[viewportNodeIndex(rows)] || null;
    if (!row) return 0;
    var blocks = state.payload.publication.source_document.blocks || [];
    var index = blocks.findIndex(function (block) {
      return block.block_id === row.dataset.blockId;
    });
    return index < 0 ? 0 : index;
  }

  function viewportNodeIndex(nodes) {
    if (!nodes.length) return -1;
    var viewportHeight = window.innerHeight ||
      document.documentElement.clientHeight || 0;
    var viewportTop = 0;
    var tools = document.querySelector(".alc-fixed-tools");
    if (tools && typeof tools.getBoundingClientRect === "function") {
      viewportTop = Math.max(0, tools.getBoundingClientRect().bottom + 4);
    }
    var last = 0;
    for (var index = 0; index < nodes.length; index += 1) {
      if (typeof nodes[index].getBoundingClientRect !== "function") continue;
      last = index;
      var rectangle = nodes[index].getBoundingClientRect();
      if (rectangle.bottom > viewportTop && rectangle.top < viewportHeight) {
        return index;
      }
      if (rectangle.top >= viewportHeight) return index;
    }
    return last;
  }

  function readableSpeechIndex(index, direction) {
    var step = direction < 0 ? -1 : 1;
    while (
      index >= 0 && index < state.speechQueue.length &&
      !speechSegmentText(state.speechQueue[index])
    ) {
      index += step;
    }
    return index >= 0 && index < state.speechQueue.length ? index : -1;
  }

  function speakSpeechIndex(index, direction) {
    index = readableSpeechIndex(index, direction);
    if (index < 0 || index >= state.speechQueue.length) {
      finishSpeech(true, "");
      return;
    }
    state.speechGeneration += 1;
    var generation = state.speechGeneration;
    window.speechSynthesis.cancel();
    var segment = state.speechQueue[index];
    var text = speechSegmentText(segment);
    var utterance = new window.SpeechSynthesisUtterance(text);
    var voice = selectedSpeechVoice(segment);
    if (voice) {
      utterance.voice = voice;
      utterance.lang = voice.lang || segment.language;
    } else if (segment.language) {
      utterance.lang = segment.language;
    }
    utterance.rate = state.speechRate;
    utterance.onend = function () {
      if (
        generation !== state.speechGeneration ||
        state.speechUtterance !== utterance
      ) return;
      if (state.speechLoopMode === "one") speakSpeechIndex(index);
      else if (index + 1 < state.speechQueue.length) speakSpeechIndex(index + 1);
      else if (state.speechLoopMode === "all") speakSpeechIndex(0);
      else finishSpeech(true, "");
    };
    utterance.onerror = function (event) {
      if (
        generation !== state.speechGeneration ||
        state.speechUtterance !== utterance
      ) return;
      finishSpeech(false, String(event.error || "unknown"));
    };
    state.speechIndex = index;
    state.speechUtterance = utterance;
    state.speechPlaying = true;
    state.speechPaused = false;
    var dock = document.getElementById("alc-speech-dock");
    if (dock) {
      dock.hidden = false;
      document.body.classList.add("alc-speech-dock-open");
    }
    setSpeechActiveNode(speechSegmentNode(segment));
    setSpeechStatus("", false);
    updateSpeechControls();
    try {
      window.speechSynthesis.speak(utterance);
    } catch (error) {
      finishSpeech(false, String(error.message || error));
    }
  }

  function speechProgressText(index, total) {
    return labels().speechProgress
      .replace("{current}", String(index + 1))
      .replace("{total}", String(total));
  }

  function toggleSpeechPause() {
    if (!state.speechPlaying) return;
    if (state.speechPaused) {
      window.speechSynthesis.resume();
      state.speechPaused = false;
    } else {
      window.speechSynthesis.pause();
      state.speechPaused = true;
    }
    updateSpeechControls();
  }

  function moveSpeech(offset) {
    if (!state.speechPlaying || !state.speechQueue.length) return;
    var target = readableSpeechIndex(state.speechIndex + offset, offset);
    if (target < 0) return;
    speakSpeechIndex(target, offset);
  }

  function stopSpeech(showReady) {
    state.speechGeneration += 1;
    if (state.speechSupported) window.speechSynthesis.cancel();
    state.speechQueue = [];
    state.speechIndex = -1;
    state.speechUtterance = null;
    state.speechPlaying = false;
    state.speechPaused = false;
    setSpeechActiveNode(null);
    if (showReady) setSpeechStatus(labels().speechReady, false);
    updateSpeechControls();
  }

  function finishSpeech(completed, error) {
    state.speechGeneration += 1;
    state.speechUtterance = null;
    state.speechPlaying = false;
    state.speechPaused = false;
    setSpeechActiveNode(null);
    setSpeechStatus(
      completed ? labels().speechFinished : labels().speechError + error,
      !completed
    );
    updateSpeechControls();
  }

  function setSpeechActiveNode(node) {
    if (state.speechActiveNode) {
      state.speechActiveNode.classList.remove("is-speaking");
    }
    state.speechActiveNode = node || null;
    if (!node) return;
    node.classList.add("is-speaking");
    if (typeof node.scrollIntoView === "function") {
      var reduced = window.matchMedia &&
        window.matchMedia("(prefers-reduced-motion: reduce)").matches;
      node.scrollIntoView({block: "center", behavior: reduced ? "auto" : "smooth"});
    }
  }

  function setSpeechStatus(value, error) {
    var root = document.getElementById("alc-speech-status");
    if (!root) return;
    state.speechStatus = value || "";
    state.speechStatusError = Boolean(error);
    root.textContent = state.speechStatus;
    root.dataset.kind = state.speechStatusError ? "error" : "info";
    if (state.speechReady) syncSpeechPlayers();
  }

  function updateSpeechControls() {
    if (!state.speechReady) return;
    syncSpeechPlayers();
  }

  function renderContents(list, sections, strings) {
    var contentsHeading = document.getElementById("alc-contents-heading");
    contentsHeading.textContent = strings.contents;
    sections.forEach(function (section) {
      var item = element("li");
      item.dataset.level = String(section.level);
      var link = element("a");
      link.href = section.anchor_block_id === state.primaryTitleBlockId ?
        "#alc-book-header" : "#block-" + safeToken(section.anchor_block_id);
      link.dataset.blockId = section.anchor_block_id;
      link.dataset.sourceTitle = String(section.title || "");
      appendTocTitle(link, section.title);
      item.appendChild(link);
      list.appendChild(item);
    });
    if ((state.payload.publication.glossary || []).length) {
      appendContentsLink(list, strings.glossary, "#alc-glossary");
    }
    if ((state.payload.publication.bibliography || []).length) {
      appendContentsLink(list, strings.references, "#alc-references");
    }
    appendSupplementCoverage(list);
    appendEditorialReview(list);
  }

  function appendSupplementCoverage(list) {
    var profile = state.payload.publication.reader_profile || {};
    var coverage = profile.supplement_coverage;
    if (!coverage || typeof coverage.summary !== "string") return;
    var item = element("li", "alc-supplement-coverage");
    item.appendChild(element("span", "", coverage.summary));
    var resource = resourceForLogicalName(coverage.report_logical_name);
    if (resource && typeof resource.data_uri === "string") {
      item.appendChild(document.createTextNode(" "));
      var link = element("a", "", "Download complete report");
      link.href = resource.data_uri;
      link.download = coverage.report_filename || "supplement-coverage.json";
      item.appendChild(link);
    }
    list.appendChild(item);
  }

  function appendEditorialReview(list) {
    var profile = state.payload.publication.reader_profile || {};
    var review = profile.editorial_review;
    if (!review || typeof review.summary !== "string") return;
    var item = element("li", "alc-editorial-review");
    item.appendChild(element("span", "", review.summary));
    var resource = resourceForLogicalName(review.report_logical_name);
    if (resource && typeof resource.data_uri === "string") {
      item.appendChild(document.createTextNode(" "));
      var link = element("a", "", "Download editorial review");
      link.href = resource.data_uri;
      link.download = review.report_filename || "editorial-review.json";
      item.appendChild(link);
    }
    list.appendChild(item);
  }

  function appendTocTitle(parent, value) {
    var text = String(value || "");
    var position = 0;
    while (position < text.length) {
      var match = /\\\(([^\n]+?)\\\)|\$([^$\n]+?)\$/.exec(
        text.slice(position)
      );
      if (!match) {
        parent.appendChild(document.createTextNode(text.slice(position)));
        break;
      }
      var start = position + match.index;
      if (start > position) {
        parent.appendChild(document.createTextNode(text.slice(position, start)));
      }
      var tex = match[1] === undefined ? match[2] : match[1];
      var math = element("span", "math math-inline", tex);
      math.dataset.tex = tex;
      parent.appendChild(math);
      position = start + match[0].length;
    }
    removeVisibleHtmlTags(parent);
    typeset(parent);
  }

  function updateContentsTitles() {
    var list = document.getElementById("alc-contents-list");
    if (!list || !state.md) return;
    Array.prototype.forEach.call(
      list.querySelectorAll("a[data-block-id]"),
      function (link) {
        link.replaceChildren();
        var heading = state.sourceVisible ? null : visibleHeadingForBlock(
          link.dataset.blockId
        );
        if (heading) {
          Array.prototype.forEach.call(heading.childNodes, function (child) {
            link.appendChild(child.cloneNode(true));
          });
          removeVisibleHtmlTags(link);
          decorateGlossary(link, "target");
          typeset(link);
        } else {
          appendTocTitle(link, link.dataset.sourceTitle);
        }
      }
    );
  }

  function visibleHeadingForBlock(blockId) {
    var candidates = [];
    var loadedIds = new Set();
    (state.fragmentGroups.get(blockId) || []).forEach(function (fragment) {
      loadedIds.add(fragment.fragment_id);
      candidates.push(fragment);
    });
    (state.payload.selected_heading_fragments || []).forEach(function (fragment) {
      if (fragment.target_id === blockId && !loadedIds.has(fragment.fragment_id)) {
        candidates.push(fragment);
      }
    });
    candidates.sort(function (left, right) {
      return Number(left.priority) - Number(right.priority) ||
        left.fragment_id.localeCompare(right.fragment_id);
    });
    for (var index = 0; index < candidates.length; index += 1) {
      var candidate = candidates[index];
      if (state.hiddenRoles.has(candidate.role)) continue;
      var holder = element("div");
      holder.innerHTML = state.md.render(projectGlossaryMarkdown(
        candidate.markdown_body, candidate
      ));
      var heading = holder.firstElementChild;
      if (heading && /^H[1-6]$/.test(heading.tagName)) return heading;
    }
    return null;
  }

  function appendContentsLink(list, text, href) {
    var item = element("li");
    var link = element("a", "", text);
    link.href = href;
    item.appendChild(link);
    list.appendChild(item);
  }

  function renderGlossary(main, glossary, strings) {
    if (!glossary.length) return;
    var section = element("section", "alc-appendix");
    section.id = "alc-glossary";
    section.appendChild(element("h2", "", strings.glossary));
    var dl = element("dl");
    glossary.forEach(function (entry) {
      dl.appendChild(renderGlossaryRow(entry, strings));
    });
    section.appendChild(dl);
    main.appendChild(section);
  }

  function renderGlossaryRow(entry, strings) {
    var row = element("div", "alc-glossary-row");
    var entryId = glossaryEntryId(entry);
    var editable = glossaryEntryEditableInState(entry);
    var draft = state.activeGlossaryDraft;
    var editing = Boolean(editable && draft && draft.entryId === entryId);
    if (entryId) row.dataset.glossaryEntryId = entryId;

    if (editing) {
      row.classList.add("is-editable", "is-inline-editing");
      row.appendChild(glossaryInlineSource(entry, strings, draft));
      row.appendChild(glossaryInlineField(
        "textarea", "alc-glossary-inline-input", strings.translatedTerm,
        entry[glossaryTranslatedKey(entry)] || "", draft.translated_term,
        function (value) {
          draft.translated_term = value;
          updateDraftSaveButtons(row);
        }
      ));
      row.appendChild(glossaryInlineField(
        "textarea", "alc-inline-markdown alc-glossary-inline-definition",
        strings.definition,
        entry.definition || "", draft.definition, function (value) {
          draft.definition = value;
          updateDraftSaveButtons(row);
        }, renderGlossaryDefinition, draft, strings
      ));
      return row;
    }

    var original = element("dt", "", entry.term || entry.source_term || "");
    decorateGlossary(original, "source");
    row.appendChild(original);

    var translated = element("dd", "alc-glossary-translation");
    var recoveredTranslatedTerm = appendGlossaryTranslatedTerm(
      translated, entry.translated_term || entry.translation || ""
    );
    decorateGlossary(translated, "target");
    if (recoveredTranslatedTerm) typeset(translated);
    row.appendChild(translated);
    var definition = element("dd", "alc-glossary-definition");
    definition.appendChild(renderGlossaryDefinition(entry.definition || ""));
    row.appendChild(definition);
    if (editable) {
      row.classList.add("is-editable");
      row.addEventListener("click", function (event) {
        handleGlossaryEntryClick(event, entry);
      });
      row.addEventListener("dblclick", function (event) {
        handleGlossaryEntryDoubleClick(event, entry);
      });
      row.appendChild(renderGlossaryCardActions(entry));
      setupTouchCardActions(row, interactiveGlossaryEditTarget);
    }
    return row;
  }

  function renderGlossaryInlineHeader(labelText, draft, strings, actionClass) {
    var header = element("div", "alc-glossary-inline-column-header");
    header.appendChild(element(
      "span", "alc-glossary-inline-column-label", labelText
    ));
    if (draft) {
      header.appendChild(renderGlossaryInlineActions(
        draft, strings,
        actionClass || "alc-glossary-inline-desktop-actions"
      ));
    }
    return header;
  }

  function renderGlossaryInlineActions(draft, strings, className) {
    var actions = element(
      "div", "alc-fragment-actions alc-inline-actions " + className
    );
    actions.appendChild(element(
      "span", "alc-fragment-meta",
      strings.glossaryTerm + " · v" + String(draft.baseRevision)
    ));
    appendInlineActions(actions);
    return actions;
  }

  function glossaryInlineSource(entry, strings, draft) {
    var cell = element(
      "dt", "alc-glossary-inline-column alc-glossary-inline-source"
    );
    cell.appendChild(renderGlossaryInlineHeader(
      strings.source, draft, strings, "alc-glossary-inline-mobile-actions"
    ));
    var value = element(
      "div", "alc-glossary-inline-source-value", glossarySourceTerm(entry)
    );
    decorateGlossary(value, "source");
    cell.appendChild(value);
    return cell;
  }

  function glossaryInlineField(
    tag, className, labelText, savedValue, value, onInput, renderSaved,
    draft, strings
  ) {
    var cell = element(
      "dd", "alc-glossary-inline-column alc-glossary-inline-cell"
    );
    if (className.indexOf("alc-glossary-inline-definition") >= 0) {
      cell.classList.add("is-definition");
    }
    cell.appendChild(renderGlossaryInlineHeader(labelText, draft, strings));
    var saved = renderSaved ?
      renderSaved(savedValue) : element("span", "", savedValue);
    saved.classList.add("alc-glossary-saved-value");
    var control = element(tag, className);
    if (tag === "input") control.type = "text";
    control.setAttribute("aria-label", labelText);
    control.value = value;
    control.spellcheck = true;
    control.addEventListener("input", function () {
      onInput(control.value);
      if (className.indexOf("alc-glossary-inline-input") >= 0) {
        clearGlossaryValidationError();
      }
    });
    cell.appendChild(saved);
    cell.appendChild(control);
    return cell;
  }

  function renderBibliography(main, bibliography, strings) {
    if (!bibliography.length) return;
    var section = element("section", "alc-appendix");
    section.id = "alc-references";
    section.appendChild(element("h2", "", strings.references));
    var list = element("ol", "alc-reference-list");
    bibliographyIndex().groups.forEach(function (group) {
      var entry = group.entry;
      var item = element("li");
      var id = group.targetId;
      if (id) item.id = "reference-" + id;
      var title = entry.title || entry.source || id;
      var source = entry.source || entry.url || "";
      if (/^https?:\/\//i.test(source)) {
        var link = element("a", "", title);
        link.href = source;
        link.rel = "noopener noreferrer";
        item.appendChild(link);
      } else {
        item.appendChild(element("strong", "", title));
      }
      if (source && source !== title) {
        item.appendChild(document.createTextNode(" — " + source));
      }
      (entry.dois || []).forEach(function (doi) {
        item.appendChild(document.createTextNode(" DOI: " + doi));
      });
      (entry.arxiv_ids || []).forEach(function (identifier) {
        item.appendChild(document.createTextNode(" arXiv: " + identifier));
      });
      list.appendChild(item);
    });
    section.appendChild(list);
    main.appendChild(section);
  }

  function renderDiagnostics(main) {
    main.replaceChildren();
    state.diagnostics.forEach(function (value) {
      main.appendChild(element("p", "alc-diagnostic", value));
    });
  }

  function glossarySurfaces(layer) {
    if (state.glossarySurfaceCache[layer]) {
      return state.glossarySurfaceCache[layer];
    }
    var values = [];
    (state.payload.publication.glossary || []).forEach(function (entry) {
      var surface = layer === "source" ?
        (entry.term || entry.source_term) :
        (entry.translated_term || entry.translation);
      if (!surface) return;
      values.push({
        surface: String(surface),
        folded: String(surface).toLocaleLowerCase(),
        entry: entry,
        latin: /^[A-Za-z0-9_ -]+$/.test(String(surface))
      });
    });
    values.sort(function (left, right) {
      return right.surface.length - left.surface.length ||
        left.surface.localeCompare(right.surface);
    });
    state.glossarySurfaceCache[layer] = values;
    return state.glossarySurfaceCache[layer];
  }

  function decorateGlossary(root, layer) {
    var surfaces = glossarySurfaces(layer);
    if (!surfaces.length) return;
    var walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
    var nodes = [];
    var node;
    while ((node = walker.nextNode())) nodes.push(node);
    nodes.forEach(function (textNode) {
      var parent = textNode.parentElement;
      if (!parent || parent.closest(
        "code, pre, a, .math, .glossary-term, .alc-reference-list"
      )) return;
      replaceGlossaryText(textNode, surfaces);
    });
  }

  function replaceGlossaryText(textNode, surfaces) {
    var value = textNode.nodeValue || "";
    var folded = value.toLocaleLowerCase();
    var matches = [];
    var cursor = 0;
    while (cursor < value.length) {
      var found = null;
      surfaces.some(function (item) {
        if (folded.slice(cursor, cursor + item.folded.length) !== item.folded) {
          return false;
        }
        if (item.latin && !hasLatinBoundaries(value, cursor, item.surface.length)) {
          return false;
        }
        found = item;
        return true;
      });
      if (found) {
        var same = surfaces.filter(function (item) {
          return item.folded === found.folded;
        });
        matches.push({start: cursor, end: cursor + found.surface.length, entries: same});
        cursor += found.surface.length;
      } else {
        cursor += 1;
      }
    }
    if (!matches.length) return;
    var fragment = document.createDocumentFragment();
    cursor = 0;
    matches.forEach(function (match) {
      if (match.start > cursor) {
        fragment.appendChild(document.createTextNode(value.slice(cursor, match.start)));
      }
      var term = element("span", "glossary-term", value.slice(match.start, match.end));
      term.tabIndex = 0;
      term._alcGlossaryEntries = match.entries.map(function (item) {
        return item.entry;
      });
      term.dataset.glossaryTooltip = tooltipText(
        term._alcGlossaryEntries
      );
      term.setAttribute("aria-describedby", "alc-tooltip");
      fragment.appendChild(term);
      cursor = match.end;
    });
    if (cursor < value.length) fragment.appendChild(document.createTextNode(value.slice(cursor)));
    textNode.replaceWith(fragment);
  }

  function hasLatinBoundaries(value, start, length) {
    var before = start > 0 ? value.charAt(start - 1) : "";
    var after = start + length < value.length ? value.charAt(start + length) : "";
    return !/[A-Za-z0-9_]/.test(before) && !/[A-Za-z0-9_]/.test(after);
  }

  function tooltipText(entries) {
    var strings = labels();
    return glossaryTooltipModels(entries).map(function (entry) {
      return strings.originalTerm + ": " + entry.source +
        "\n" + strings.translatedTerm + ": " +
        entry.translated +
        "\n" + strings.definition + ": " +
        glossaryDefinitionPlainText(entry.definition);
    }).join("\n\n");
  }

  function glossaryTooltipModels(entries) {
    return (entries || []).map(function (entry) {
      return {
        source: String(entry.term || entry.source_term || ""),
        translated: String(
          entry.translated_term || entry.translation || ""
        ),
        definition: String(entry.definition || "")
      };
    });
  }

  function renderGlossaryTooltip(entries) {
    var strings = labels();
    var content = document.createDocumentFragment();
    glossaryTooltipModels(entries).forEach(function (entry) {
      var group = element("section", "alc-tooltip-entry");
      var source = element("div", "alc-tooltip-line");
      source.appendChild(element(
        "strong", "alc-tooltip-label", strings.originalTerm + ": "
      ));
      source.appendChild(document.createTextNode(entry.source));
      group.appendChild(source);
      var translated = element("div", "alc-tooltip-line");
      translated.appendChild(element(
        "strong", "alc-tooltip-label", strings.translatedTerm + ": "
      ));
      var recoveredTranslatedTerm = appendGlossaryTranslatedTerm(
        translated, entry.translated
      );
      if (recoveredTranslatedTerm) typeset(translated);
      group.appendChild(translated);
      var definition = element("div", "alc-tooltip-definition");
      definition.appendChild(element(
        "strong", "alc-tooltip-label", strings.definition + ":"
      ));
      definition.appendChild(renderGlossaryDefinition(
        entry.definition, {decorateGlossary: false}
      ));
      group.appendChild(definition);
      content.appendChild(group);
    });
    return content;
  }

  function katexTex(value) {
    var tex = String(value || "");
    if (/\\begin\s*\{[^{}]+\}/.test(tex)) return tex;
    for (var index = 0; index < tex.length; index += 1) {
      if (tex.charAt(index) !== "&") continue;
      var slashCount = 0;
      var cursor = index - 1;
      while (cursor >= 0 && tex.charAt(cursor) === "\\") {
        slashCount += 1;
        cursor -= 1;
      }
      if (slashCount % 2 === 0) {
        return "\\begin{aligned}" + tex + "\\end{aligned}";
      }
    }
    return tex;
  }

  function katexSemanticMacros() {
    return {"\\arcdeg": "^{\\circ}"};
  }

  function repairMatrixShorthand(value) {
    var tex = String(value || "");
    var opening = /\\left\s*(\[|\()\s*\{\s*([clr](?:\s*[clr])*)\s*\}/g;
    var edits = [];
    var match;
    while ((match = opening.exec(tex))) {
      var depth = 1;
      var closingIndex = -1;
      var token = /\\(?:left|right)\b/g;
      token.lastIndex = opening.lastIndex;
      var delimiter;
      while ((delimiter = token.exec(tex))) {
        if (delimiter[0] === "\\left") {
          depth += 1;
        } else {
          depth -= 1;
          if (depth === 0) {
            closingIndex = delimiter.index;
            break;
          }
        }
      }
      if (closingIndex < 0) continue;
      edits.push({
        start: match.index,
        end: opening.lastIndex,
        value: "\\left" + match[1] + "\\begin{array}{" +
          match[2].replace(/\s+/g, "") + "}"
      });
      edits.push({
        start: closingIndex,
        end: closingIndex,
        value: "\\end{array}"
      });
    }
    edits.sort(function (left, right) {
      return right.start - left.start || right.end - left.end;
    });
    edits.forEach(function (edit) {
      tex = tex.slice(0, edit.start) + edit.value + tex.slice(edit.end);
    });
    return tex;
  }

  function repairRepeatedSuperscripts(value) {
    var tex = String(value || "");
    var repeated = /((?:\\[A-Za-z]+|[A-Za-z0-9])(?:_(?:\{[^{}]*\}|\\[A-Za-z]+|.))?)(\^(?:\{[^{}]*\}|\\[A-Za-z]+|.))(\^(?:\{[^{}]*\}|\\[A-Za-z]+|.)|')/g;
    return tex.replace(repeated, function (_match, base, first, second) {
      return "{" + base + first + "}" + second;
    });
  }

  function repairGroupedSizeDelimiters(value) {
    var grouped = /\\(big|Big|bigg|Bigg)(l|r)?\s*\{(\\[A-Za-z]+|\(|\)|\[|\]|\||\.|\/)\}/g;
    return String(value || "").replace(grouped, function (
      _match, size, side, delimiter
    ) {
      return "\\" + size + (side || "") + delimiter;
    });
  }

  function repairOldStyleMathShifts(value) {
    return String(value || "").replace(
      /\\mbox\s*\{\$([\s\S]*?)\$\}/g,
      function (_match, math) { return "{" + math + "}"; }
    );
  }

  function repairTextBoxes(value) {
    // KaTeX does not expose legacy plain-TeX \mbox.  After removing nested
    // math shifts, its text-mode equivalent preserves authored labels.
    return String(value || "").replace(/\\mbox\b/g, "\\text");
  }

  function repairLatexmlProjection(value) {
    return repairUnicodeCodePointCommands(value)
      .replace(/\\penalty(?![A-Za-z@])/g, "")
      .replace(
        /\\color\s*\[\s*rgb\s*\]\s*\{\s*0(?:\.0+)?\s*,\s*0(?:\.0+)?\s*,\s*0(?:\.0+)?\s*\}/g,
        ""
      );
  }

  function repairUnicodeCodePointCommands(value) {
    return String(value || "").replace(
      /\\unicode\s*\{\s*[xX]([0-9A-Fa-f]{1,6})\s*\}/g,
      function (match, hexadecimal) {
        var codePoint = Number.parseInt(hexadecimal, 16);
        if (
          !Number.isInteger(codePoint) || codePoint < 0xa0 ||
          codePoint > 0x10ffff ||
          (codePoint >= 0xd800 && codePoint <= 0xdfff)
        ) return match;
        var character = String.fromCodePoint(codePoint);
        if (!/^[\p{L}\p{M}\p{N}\p{P}\p{S}]$/u.test(character)) return match;
        return "\\text{" + character + "}";
      }
    );
  }

  function repairArrayEnvironment(value) {
    var tex = String(value || "").replace(
      /\\begin\s*\{array\}\s*\[\s*\]\s*/g,
      "\\begin{array}"
    );
    var stripped = /^\s*\[\s*\]\s*\{([clr|\s]+)\}([\s\S]*)$/.exec(tex);
    if (stripped && stripped[2].indexOf("&") >= 0) {
      return "\\begin{array}{" + stripped[1].replace(/\s+/g, "") + "}" +
        stripped[2] + "\\end{array}";
    }
    return tex;
  }

  function katexCandidates(value) {
    var primary = katexTex(value);
    var latexmlProjection = repairLatexmlProjection(value);
    var repairedLatexml = katexTex(latexmlProjection);
    var repairedMathShifts = katexTex(
      repairOldStyleMathShifts(latexmlProjection)
    );
    var repairedTextBoxes = katexTex(
      repairTextBoxes(repairOldStyleMathShifts(latexmlProjection))
    );
    // Repair a stripped array before generic bare-ampersand handling wraps it
    // as an aligned equation.
    var repairedArrays = katexTex(
      repairArrayEnvironment(
        repairTextBoxes(
          repairOldStyleMathShifts(latexmlProjection)
        )
      )
    );
    var repaired = repairMatrixShorthand(repairedArrays);
    var repairedScripts = repairRepeatedSuperscripts(repaired)
      .replace(/\u000crac/g, "\\frac");
    var repairedDelimiters = repairGroupedSizeDelimiters(repairedScripts);
    var fixedSizeDelimiters = repairedDelimiters
      .replace(/\\left\b/g, "\\bigl")
      .replace(/\\right\b/g, "\\bigr");
    return [
      primary,
      repairedLatexml,
      repairedMathShifts,
      repairedTextBoxes,
      repairedArrays,
      repaired,
      repairedScripts,
      repairedDelimiters,
      fixedSizeDelimiters
    ].filter(function (candidate, index, values) {
      return values.indexOf(candidate) === index;
    });
  }

  function typeset(root) {
    if (!window.katex || typeof window.katex.render !== "function") return;
    var scope = root.querySelectorAll ? root : document;
    scope.querySelectorAll(".math[data-tex]").forEach(function (node) {
      if (node.dataset.alcTypeset === "true") return;
      try {
        var settings = {
          displayMode: node.classList.contains("math-display"),
          throwOnError: true,
          strict: "warn",
          macros: katexSemanticMacros()
        };
        var candidates = katexCandidates(node.dataset.tex);
        var rendered = candidates.some(function (candidate) {
          try {
            window.katex.render(candidate, node, settings);
            return true;
          } catch (_candidateError) {
            return false;
          }
        });
        if (!rendered) {
          settings.throwOnError = false;
          window.katex.render(candidates[0] || "", node, settings);
          node.classList.add("math-error");
        }
        node.dataset.alcTypeset = "true";
      } catch (_error) {
        node.textContent = node.dataset.tex || "";
        node.classList.add("math-error");
      }
    });
  }

  function startProgressiveRendering() {
    setupChunkObserver();
    setupHydrationActivity();
    scheduleIdleHydration();
  }

  function setupChunkObserver() {
    if (!("IntersectionObserver" in window) || state.chunkObserver) return;
    state.chunkObserver = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (!entry.isIntersecting) return;
        var chunk = state.renderPlan.find(function (item) {
          return item.chunk_id === entry.target.dataset.chunkId;
        });
        try {
          renderChunk(chunk);
        } catch (error) {
          failProgressiveRender(error);
        }
      });
    }, {rootMargin: "150% 0px", threshold: 0});
    state.renderPlan.forEach(function (chunk) {
      if (state.renderedChunkIds.has(chunk.chunk_id)) return;
      state.chunkObserver.observe(state.chunkNodes.get(chunk.chunk_id));
    });
  }

  function scheduleIdleHydration() {
    if (
      state.idleRenderHandle !== null ||
      state.hydrationQuietTimer !== null ||
      document.body.dataset.alcRenderComplete === "true"
    ) {
      return;
    }
    state.hydrationQuietTimer = window.setTimeout(function () {
      state.hydrationQuietTimer = null;
      requestIdleHydration();
    }, 2000);
  }

  function requestIdleHydration() {
    if (
      state.idleRenderHandle !== null ||
      document.body.dataset.alcRenderComplete === "true"
    ) {
      return;
    }
    var generation = state.idleRenderGeneration;
    var work = function (deadline) {
      state.idleRenderHandle = null;
      if (generation !== state.idleRenderGeneration) return;
      if (deadline && deadline.timeRemaining() < 12) {
        requestIdleHydration();
        return;
      }
      var chunk = nextHydrationChunk();
      if (!chunk) {
        updateRenderComplete();
        return;
      }
      try {
        renderChunk(chunk);
      } catch (error) {
        failProgressiveRender(error);
        return;
      }
      requestIdleHydration();
    };
    if (typeof window.requestIdleCallback === "function") {
      state.idleRenderUsesCallback = true;
      state.idleRenderHandle = window.requestIdleCallback(work);
    } else {
      state.idleRenderUsesCallback = false;
      state.idleRenderHandle = window.setTimeout(work, 250);
    }
  }

  function noteHydrationActivity() {
    if (state.hashCalibration) state.hashCalibration = null;
    cancelIdleHydration();
    scheduleIdleHydration();
  }

  function setupHydrationActivity() {
    if (state.hydrationActivityReady) return;
    ["wheel", "touchstart", "keydown", "pointerdown"].forEach(function (name) {
      window.addEventListener(name, noteHydrationActivity, {passive: true});
    });
    state.hydrationActivityReady = true;
  }

  function nextHydrationChunk() {
    for (var index = 0; index < state.hydrationOrder.length; index += 1) {
      var id = state.hydrationOrder[index];
      if (state.renderedChunkIds.has(id)) continue;
      return state.renderPlan.find(function (chunk) {
        return chunk.chunk_id === id;
      }) || null;
    }
    return state.renderPlan.find(function (chunk) {
      return !state.renderedChunkIds.has(chunk.chunk_id);
    }) || null;
  }

  function cancelIdleHydration() {
    state.idleRenderGeneration += 1;
    if (state.hydrationQuietTimer !== null) {
      window.clearTimeout(state.hydrationQuietTimer);
      state.hydrationQuietTimer = null;
    }
    if (state.idleRenderHandle === null) return;
    if (
      state.idleRenderUsesCallback &&
      typeof window.cancelIdleCallback === "function"
    ) {
      window.cancelIdleCallback(state.idleRenderHandle);
    } else {
      window.clearTimeout(state.idleRenderHandle);
    }
    state.idleRenderHandle = null;
  }

  function stopProgressiveRendering() {
    if (state.chunkObserver) state.chunkObserver.disconnect();
    state.chunkObserver = null;
    cancelIdleHydration();
    state.readerShellReady = false;
  }

  function updateRenderComplete() {
    var complete = state.renderPlan.length > 0 &&
      state.renderPlan.every(function (chunk) {
        return state.renderedChunkIds.has(chunk.chunk_id);
      });
    document.body.dataset.alcRenderComplete = String(complete);
    if (!complete) return;
    if (state.chunkObserver) state.chunkObserver.disconnect();
    state.chunkObserver = null;
    cancelIdleHydration();
  }

  function failProgressiveRender(error) {
    stopProgressiveRendering();
    document.body.dataset.alcRenderReady = "error";
    var message = String(error.message || error);
    if (state.diagnosticsRoot) {
      state.diagnosticsRoot.prepend(
        element("p", "alc-diagnostic", message)
      );
    }
  }

  function setupProgressiveNavigation() {
    if (state.navigationReady) return;
    document.addEventListener("click", function (event) {
      var link = event.target.closest && event.target.closest('a[href^="#"]');
      if (!link) return;
      var href = link.getAttribute("href") || "";
      var targetId = hashTargetId(href);
      if (
        targetId !== "alc-book-header" &&
        !chunkForTargetId(targetId)
      ) return;
      event.preventDefault();
      activateHashTarget(href, true, event.detail === 0);
    });
    window.addEventListener("hashchange", function () {
      activateHashTarget(window.location.hash, false);
    });
    window.addEventListener("popstate", function () {
      activateHashTarget(window.location.hash, false);
    });
    state.navigationReady = true;
  }

  function activateHashTarget(hash, updateHistory, keyboardNavigation) {
    var requestedTargetId = hashTargetId(hash);
    var targetId = canonicalReaderTargetId(requestedTargetId);
    var canonicalHash = targetId === requestedTargetId ? hash : "#" + targetId;
    if (targetId === "alc-book-header") {
      if (updateHistory) {
        if (window.location.hash === canonicalHash) {
          window.history.replaceState(null, "", canonicalHash);
        } else {
          window.history.pushState(null, "", canonicalHash);
        }
      }
      state.hashCalibration = null;
      scrollToHashTarget(targetId, keyboardNavigation === true);
      return true;
    }
    var chunk = chunkForTargetId(targetId);
    if (!chunk) return false;
    revealSourceTarget(targetId);
    renderChunk(chunk);
    armHashCalibration(canonicalHash, keyboardNavigation === true);
    if (updateHistory) {
      if (window.location.hash === canonicalHash) {
        window.history.replaceState(null, "", canonicalHash);
      } else {
        window.history.pushState(null, "", canonicalHash);
      }
    } else if (targetId !== requestedTargetId) {
      window.history.replaceState(null, "", canonicalHash);
    }
    scrollToHashTarget(targetId, keyboardNavigation === true);
    return true;
  }

  function scrollToReaderTop() {
    window.requestAnimationFrame(function () {
      var root = document.documentElement;
      var previousBehavior = root.style.scrollBehavior;
      root.style.scrollBehavior = "auto";
      window.scrollTo({top: 0, left: 0, behavior: "auto"});
      root.style.scrollBehavior = previousBehavior;
    });
  }

  function armHashCalibration(hash, keyboardNavigation) {
    var targetId = hashTargetId(hash);
    if (!targetId || !chunkForTargetId(targetId)) return;
    state.hashCalibration = {
      targetId: targetId,
      keyboardNavigation: keyboardNavigation === true
    };
    recalibrateHashTarget();
  }

  function recalibrateHashTarget() {
    var calibration = state.hashCalibration;
    if (!calibration) return;
    scrollToHashTarget(
      calibration.targetId, calibration.keyboardNavigation === true
    );
  }

  function scrollToHashTarget(targetId, keyboardNavigation) {
    window.requestAnimationFrame(function () {
      var target = document.getElementById(targetId);
      if (!target) return;
      var root = document.documentElement;
      var previousBehavior = root.style.scrollBehavior;
      root.style.scrollBehavior = "auto";
      target.scrollIntoView({block: "start", behavior: "auto"});
      root.style.scrollBehavior = previousBehavior;
      if (target.classList.contains("alc-source-navigation-target")) {
        document.querySelectorAll(".alc-keyboard-navigation-target").forEach(
          function (node) {
            node.classList.remove("alc-keyboard-navigation-target");
          }
        );
        target.classList.toggle(
          "alc-keyboard-navigation-target", keyboardNavigation === true
        );
        document.querySelectorAll(".alc-reference-target-active").forEach(
          function (node) { node.classList.remove("alc-reference-target-active"); }
        );
        target.classList.add("alc-reference-target-active");
        try {
          target.focus({preventScroll: true});
        } catch (_error) {
          target.focus();
        }
        window.setTimeout(function () {
          target.classList.remove("alc-reference-target-active");
        }, 2400);
      }
    });
  }

  function setupPrintRendering() {
    if (state.printReady) return;
    window.addEventListener("beforeprint", renderAllChunks);
    state.printReady = true;
  }

  function setupContents() {
    var shell = document.getElementById("alc-shell");
    var contents = document.getElementById("alc-contents");
    var toggle = document.getElementById("alc-contents-toggle");
    var resizer = document.getElementById("alc-contents-resizer");
    var mobile = window.matchMedia("(max-width: 899px)");
    var strings = labels();
    var open = !mobile.matches;
    var rootFontSize = parseFloat(
      window.getComputedStyle(document.documentElement).fontSize
    ) || 16;
    var minimumWidth = 12 * rootFontSize;
    var preferredMaximumWidth = 32 * rootFontSize;
    var width = 18 * rootFontSize;
    var dragging = false;
    var dragStartX = 0;
    var dragStartWidth = width;
    var collapseOvershoot = 2 * rootFontSize;

    function maximumWidth() {
      return Math.max(
        minimumWidth,
        Math.min(preferredMaximumWidth, window.innerWidth * .45)
      );
    }

    function setWidth(value) {
      width = Math.min(maximumWidth(), Math.max(minimumWidth, Number(value)));
      shell.style.setProperty("--alc-contents-width", Math.round(width) + "px");
      resizer.setAttribute("aria-valuemin", String(Math.round(minimumWidth)));
      resizer.setAttribute("aria-valuemax", String(Math.round(maximumWidth())));
      resizer.setAttribute("aria-valuenow", String(Math.round(width)));
      resizer.setAttribute("aria-valuetext", Math.round(width) + " px");
    }

    function setOpen(value) {
      open = Boolean(value);
      shell.classList.toggle("contents-collapsed", !open);
      contents.setAttribute("aria-hidden", String(!open));
      toggle.setAttribute("aria-expanded", String(open));
      labelToolButton(toggle, open ? strings.collapse : strings.expand);
      if (open) setWidth(width);
    }

    function stopDragging() {
      if (!dragging) return;
      dragging = false;
      shell.classList.remove("is-resizing-contents");
      window.removeEventListener("pointermove", drag);
      window.removeEventListener("pointerup", stopDragging);
      window.removeEventListener("pointercancel", stopDragging);
    }

    function drag(event) {
      if (!dragging) return;
      var next = dragStartWidth + Number(event.clientX) - dragStartX;
      if (next < minimumWidth - collapseOvershoot) {
        stopDragging();
        setOpen(false);
        return;
      }
      setWidth(next);
      if (typeof event.preventDefault === "function") event.preventDefault();
    }

    resizer.title = strings.resizeContents;
    resizer.setAttribute("aria-label", strings.resizeContents);
    resizer.addEventListener("pointerdown", function (event) {
      if (mobile.matches || !open || event.button !== 0) return;
      dragging = true;
      dragStartX = Number(event.clientX);
      dragStartWidth = width;
      shell.classList.add("is-resizing-contents");
      window.addEventListener("pointermove", drag);
      window.addEventListener("pointerup", stopDragging);
      window.addEventListener("pointercancel", stopDragging);
      if (typeof event.preventDefault === "function") event.preventDefault();
    });
    resizer.addEventListener("keydown", function (event) {
      var next = width;
      if (event.key === "ArrowLeft") next -= rootFontSize;
      else if (event.key === "ArrowRight") next += rootFontSize;
      else if (event.key === "Home") next = minimumWidth;
      else if (event.key === "End") next = maximumWidth();
      else return;
      event.preventDefault();
      if (next < minimumWidth) setOpen(false);
      else setWidth(next);
    });
    window.addEventListener("resize", function () {
      if (open && !mobile.matches) setWidth(width);
    });
    if (typeof mobile.addEventListener === "function") {
      mobile.addEventListener("change", function (event) {
        if (event.matches) setOpen(false);
      });
    }
    if (typeof document.addEventListener === "function") {
      document.addEventListener("pointerdown", function (event) {
        if (!mobile.matches || !open) return;
        if (contents.contains(event.target) || toggle.contains(event.target)) return;
        setOpen(false);
      }, true);
    }
    setWidth(width);
    setOpen(open);
    toggle.onclick = function () { setOpen(!open); };
    contents.onclick = function (event) {
      if (mobile.matches && event.target.closest("a")) setOpen(false);
    };
  }

  function setupTooltip() {
    var tooltip = document.getElementById("alc-tooltip");
    var active = null;
    function close() {
      tooltip.hidden = true;
      tooltip.replaceChildren();
      active = null;
    }
    function open(term) {
      var content = term && term.dataset.glossaryTooltip;
      var entries = term && term._alcGlossaryEntries;
      if ((!entries || !entries.length) && !content) return;
      active = term;
      if (entries && entries.length) {
        tooltip.replaceChildren(renderGlossaryTooltip(entries));
      } else {
        tooltip.textContent = content;
      }
      tooltip.hidden = false;
      var termRect = term.getBoundingClientRect();
      var tipRect = tooltip.getBoundingClientRect();
      var gap = 8;
      var top = termRect.bottom + gap;
      if (top + tipRect.height > window.innerHeight - gap) {
        top = Math.max(gap, termRect.top - tipRect.height - gap);
      }
      var left = Math.min(
        Math.max(gap, termRect.left),
        Math.max(gap, window.innerWidth - tipRect.width - gap)
      );
      tooltip.style.top = Math.round(top) + "px";
      tooltip.style.left = Math.round(left) + "px";
    }
    document.addEventListener("mouseover", function (event) {
      var term = event.target.closest && event.target.closest(".glossary-term");
      if (term) open(term);
    });
    document.addEventListener("mouseout", function (event) {
      var term = event.target.closest && event.target.closest(".glossary-term");
      if (term && (!event.relatedTarget || !term.contains(event.relatedTarget))) close();
    });
    document.addEventListener("focusin", function (event) {
      if (event.target.matches && event.target.matches(".glossary-term")) open(event.target);
    });
    document.addEventListener("focusout", function (event) {
      if (event.target === active) close();
    });
    document.addEventListener("keydown", function (event) {
      if (event.key === "Escape") close();
    });
    window.addEventListener("scroll", close, {passive: true});
  }

  function captureExportTemplate() {
    state.exportStandaloneSupported = !document.querySelector(
      'script[src], link[rel~="stylesheet"][href]'
    );
    if (!state.exportStandaloneSupported) return;
    var root = document.documentElement.cloneNode(true);
    var body = root.querySelector("body");
    var readingArea = root.querySelector("#ac-document");
    var header = root.querySelector("#alc-book-header");
    var contents = root.querySelector("#alc-contents-list");
    root.querySelectorAll(
      ".alc-render-reader-chunk, .alc-render-reader-resource"
    ).forEach(function (node) { node.remove(); });
    root.querySelectorAll(
      ".alc-select-listbox, .alc-custom-select"
    ).forEach(function (node) { node.remove(); });
    if (readingArea) readingArea.replaceChildren();
    if (header) header.replaceChildren();
    if (contents) contents.replaceChildren();
    root.querySelectorAll(
      ".alc-view-panel, .alc-speech-panel, .alc-export-panel, " +
      ".alc-settings-panel, .alc-speech-dock"
    ).forEach(function (panel) { panel.hidden = true; });
    root.querySelectorAll("[aria-expanded]").forEach(function (trigger) {
      trigger.setAttribute("aria-expanded", "false");
    });
    if (body) {
      delete body.dataset.alcRenderReady;
      delete body.dataset.alcRenderComplete;
      body.dataset.alcExportSnapshot = "true";
      body.classList.remove("alc-speech-dock-open");
    }
    state.exportHtmlTemplate = "<!doctype html>\n" + root.outerHTML;
  }

  function captureInitialSelection() {
    state.initialSelectedDigests = new Map();
    state.selected.forEach(function (revision, fragmentId) {
      state.initialSelectedDigests.set(fragmentId, revision.semantic_digest);
    });
    state.initialSelectionCaptured = true;
    publishSelectedRevisionCount();
  }

  function setupExport() {
    var strings = labels();
    var control = document.querySelector(".alc-export-control");
    var trigger = document.getElementById("alc-export");
    var panel = document.getElementById("alc-export-panel");
    labelToolButton(trigger, strings.export);
    document.getElementById("alc-export-heading").textContent =
      strings.exportPanelHeading;
    document.getElementById("alc-export-markdown-heading").textContent =
      strings.markdown;
    document.getElementById("alc-export-scope-label").textContent =
      strings.markdownScope;
    document.getElementById("alc-export-content-label").textContent =
      strings.markdownContent;
    document.getElementById("alc-export-markdown-mode-label").textContent =
      strings.markdownOutput;
    document.getElementById("alc-export-markdown-file-label").textContent =
      strings.singleMarkdown;
    document.getElementById("alc-export-markdown-package-label").textContent =
      strings.markdownPackage;
    document.getElementById("alc-export-all-label").textContent =
      strings.allLatest;
    document.getElementById("alc-export-changed-label").textContent =
      strings.changedLatest;
    var markdownPackageButton = document.getElementById(
      "alc-export-markdown-package"
    );
    document.getElementById("alc-export-markdown-label").textContent =
      strings.fullMarkdown;
    var htmlButton = document.getElementById("alc-export-html");
    document.getElementById("alc-export-html-heading").textContent =
      strings.htmlExport;
    document.getElementById("alc-export-html-description").textContent =
      strings.htmlExportDescription;
    document.getElementById("alc-export-html-label").textContent =
      strings.fullHtml;
    htmlButton.title = state.exportStandaloneSupported ? "" :
      strings.exportUnavailable;
    var pdfButton = document.getElementById("alc-export-pdf");
    document.getElementById("alc-export-pdf-heading").textContent =
      strings.pdfExport;
    document.getElementById("alc-export-pdf-description").textContent =
      strings.pdfExportDescription;
    document.getElementById("alc-export-pdf-label").textContent =
      strings.printPdf;
    trigger.addEventListener("click", function () {
      if (panel.hidden) {
        openExportPanel();
      } else {
        closeExportPanel(false);
      }
    });
    document.getElementById("alc-export-scope").addEventListener(
      "change", renderExportOptions
    );
    document.getElementById("alc-export-markdown-mode").addEventListener(
      "change", renderExportOptions
    );
    markdownPackageButton.addEventListener("click", function () {
      runExport({kind: "markdown-package"});
    });
    htmlButton.addEventListener("click", function () {
      runExport({kind: "html"});
    });
    pdfButton.addEventListener("click", function () {
      runExport({kind: "pdf"});
    });
    window.addEventListener("resize", function () { positionToolPanel(panel); });
    document.addEventListener("click", function (event) {
      if (!panel.hidden && !control.contains(event.target)) closeExportPanel(false);
    });
    document.addEventListener("keydown", function (event) {
      if (event.key === "Escape" && !panel.hidden) {
        event.preventDefault();
        closeExportPanel(true);
      }
    });
    renderExportOptions();
  }

  async function openExportPanel() {
    if (state.activeDraft) {
      setStatus(labels().draftActive, "error");
      return;
    }
    if (
      state.saveInProgress ||
      state.exportInProgress ||
      state.directorySelectionInProgress
    ) {
      setStatus(labels().revisionBusy, "error");
      return;
    }
    var trigger = document.getElementById("alc-export");
    var panel = document.getElementById("alc-export-panel");
    loadAllPayload(false);
    panel.hidden = false;
    trigger.setAttribute("aria-expanded", "true");
    positionToolPanel(panel);
    if (!state.directory) {
      renderExportOptions();
      return;
    }
    state.exportInProgress = true;
    renderExportOptions();
    try {
      setStatus(labels().exportLoading);
      if (!await loadDirectoryRevisions(state.directory)) {
        throw new Error(labels().exportSyncFailed);
      }
    } catch (error) {
      setStatus(String(error.message || error), "error");
    } finally {
      state.exportInProgress = false;
      renderExportOptions();
    }
  }

  function closeExportPanel(restoreFocus) {
    var trigger = document.getElementById("alc-export");
    document.getElementById("alc-export-panel").hidden = true;
    trigger.setAttribute("aria-expanded", "false");
    if (restoreFocus) trigger.focus();
  }

  function exportScope() {
    var checked = document.querySelector(
      'input[name="alc-export-scope"]:checked'
    );
    return checked && checked.value === "changed" ? "changed" : "all";
  }

  function markdownOutputMode() {
    var checked = document.querySelector(
      'input[name="alc-export-markdown-mode"]:checked'
    );
    return checked && checked.value === "file" ? "file" : "package";
  }

  function selectedForMarkdown(scope) {
    var values = Array.from(state.selected.values()).filter(fragmentIsVisible);
    if (scope === "changed") {
      values = values.filter(function (revision) {
        return state.initialSelectedDigests.get(revision.fragment_id) !==
          revision.semantic_digest;
      });
    }
    return values;
  }

  function renderExportOptions() {
    var root = document.getElementById("alc-export-role-options");
    root.replaceChildren();
    var availableRoles = ["source"].concat(
      selectedForMarkdown("all").map(function (revision) {
        return revision.role;
      })
    );
    var publication = state.payload.publication;
    if ((publication.glossary || []).length) availableRoles.push("glossary");
    if ((publication.bibliography || []).length) availableRoles.push("references");
    var roles = orderedExportCategories(new Set(availableRoles));
    if (!state.exportMarkdownRoles) state.exportMarkdownRoles = new Set();
    roles.forEach(function (role) {
      if (!state.exportMarkdownKnownRoles.has(role)) {
        state.exportMarkdownKnownRoles.add(role);
        state.exportMarkdownRoles.add(role);
      }
    });
    var changedRoles = new Set(selectedForMarkdown("changed").map(
      function (revision) { return revision.role; }
    ));
    if (changedGlossaryEntries().length) changedRoles.add("glossary");
    var changedOnly = exportScope() === "changed";
    var usableRoles = [];
    roles.forEach(function (role) {
      var label = element("label", "alc-export-content-option");
      var input = element("input");
      input.type = "checkbox";
      input.value = role;
      input.checked = state.exportMarkdownRoles.has(role);
      var unavailable = changedOnly && (
        role === "source" || !changedRoles.has(role)
      );
      input.disabled = state.exportInProgress || unavailable;
      input.addEventListener("change", function () {
        if (input.checked) state.exportMarkdownRoles.add(role);
        else state.exportMarkdownRoles.delete(role);
        renderExportOptions();
      });
      label.appendChild(input);
      label.appendChild(element("span", "", roleLabel(role)));
      root.appendChild(label);
      if (input.checked && !unavailable) usableRoles.push(role);
    });
    var scopeControls = document.querySelectorAll(
      'input[name="alc-export-scope"]'
    );
    Array.prototype.forEach.call(scopeControls, function (input) {
      input.disabled = state.exportInProgress;
    });
    var modeControls = document.querySelectorAll(
      'input[name="alc-export-markdown-mode"]'
    );
    Array.prototype.forEach.call(modeControls, function (input) {
      input.disabled = state.exportInProgress;
    });
    var htmlButton = document.getElementById("alc-export-html");
    var markdownPackageButton = document.getElementById(
      "alc-export-markdown-package"
    );
    document.getElementById("alc-export-markdown-label").textContent =
      labels().exportMarkdownFile;
    markdownPackageButton.disabled = state.exportInProgress || !usableRoles.length;
    htmlButton.disabled = state.exportInProgress ||
      !state.exportStandaloneSupported;
    var pdfButton = document.getElementById("alc-export-pdf");
    pdfButton.disabled = state.exportInProgress ||
      typeof window.print !== "function";
  }

  async function runExport(request) {
    if (state.activeDraft) {
      setStatus(labels().draftActive, "error");
      return;
    }
    if (
      state.saveInProgress ||
      state.exportInProgress ||
      state.directorySelectionInProgress
    ) {
      setStatus(labels().revisionBusy, "error");
      return;
    }
    state.exportInProgress = true;
    renderExportOptions();
    try {
      loadAllPayload(request.kind !== "markdown-package");
      if (state.directory) {
        setStatus(labels().exportLoading);
        if (!await loadDirectoryRevisions(state.directory)) {
          throw new Error(labels().exportSyncFailed);
        }
      }
      var successStatus = labels().exportStarted;
      if (request.kind === "markdown-package") {
        var scope = exportScope();
        var markdownMode = markdownOutputMode();
        var complete = markdownMode === "file" ?
          buildPlainMarkdown(scope, state.exportMarkdownRoles) :
          buildMarkdownPackage(scope, state.exportMarkdownRoles);
        if (!complete) {
          setStatus(scope === "changed" ?
            labels().noExportChanges : labels().selectExportContent);
          return;
        }
        if (markdownMode === "file") {
          downloadText(
            exportFilename(scope === "changed" ? "changes" : "latest", "md"),
            complete,
            "text/markdown;charset=utf-8"
          );
        } else {
          downloadBlob(
            exportFilename(scope === "changed" ? "changes" : "complete", "zip"),
            complete.archive
          );
        }
      } else if (request.kind === "html") {
        if (!state.exportStandaloneSupported) {
          throw new Error(labels().exportUnavailable);
        }
        downloadText(
          exportFilename("latest", "html"),
          buildStandaloneExportHtml(),
          "text/html;charset=utf-8"
        );
      } else {
        renderAllChunks();
        closeExportPanel(false);
        window.print();
        successStatus = labels().printOpened;
      }
      if (request.kind !== "pdf") closeExportPanel(false);
      setStatus(successStatus);
    } catch (error) {
      setStatus(String(error.message || error), "error");
    } finally {
      state.exportInProgress = false;
      renderExportOptions();
    }
  }

  function orderedExportCategories(categories) {
    var preferred = [
      "source", "translation", "guide", "companion", "note",
      "glossary", "references"
    ];
    return Array.from(categories || []).sort(function (left, right) {
      var leftIndex = preferred.indexOf(left);
      var rightIndex = preferred.indexOf(right);
      if (leftIndex < 0) leftIndex = preferred.length;
      if (rightIndex < 0) rightIndex = preferred.length;
      return leftIndex - rightIndex || comparePortableText(left, right);
    });
  }

  function selectedMarkdownCategories(scope, selectedCategories) {
    var categories = new Set(selectedCategories || []);
    if (scope === "changed") {
      var changedRoles = new Set(selectedForMarkdown("changed").map(
        function (revision) { return revision.role; }
      ));
      if (changedGlossaryEntries().length) changedRoles.add("glossary");
      categories = new Set(Array.from(categories).filter(function (role) {
        return role !== "source" && changedRoles.has(role);
      }));
    } else {
      var availableValues = ["source"].concat(
        selectedForMarkdown("all").map(function (revision) {
          return revision.role;
        })
      );
      var publication = state.payload.publication;
      if ((publication.glossary || []).length) availableValues.push("glossary");
      if ((publication.bibliography || []).length) {
        availableValues.push("references");
      }
      var availableRoles = new Set(availableValues);
      categories = new Set(Array.from(categories).filter(function (role) {
        return availableRoles.has(role);
      }));
    }
    return categories;
  }

  function buildMarkdownPackage(scope, selectedCategories) {
    var categories = selectedMarkdownCategories(scope, selectedCategories);
    if (!categories.size) return null;
    var resourceValues = state.payload.resources || [];
    var resourcePaths = portableMarkdownResourcePaths(resourceValues);
    var complete = scope === "changed" ?
      buildChangedMarkdown(resourcePaths, categories) :
      buildCompleteMarkdown(resourcePaths, categories);
    if (!complete.markdown) return null;
    complete.markdown = degradeLegacyInternalMarkdownLinks(
      complete.markdown
    );
    var includedResourcePaths = markdownReferencedResourcePaths(
      complete.markdown, resourcePaths
    );
    var resources = portableMarkdownResources(
      resourceValues, includedResourcePaths
    );
    var publication = state.payload.publication;
    var manifest = {
      schema_version: "alc.render.markdown_export.v1",
      document: "document.md",
      scope: scope === "changed" ? "changed" : "all",
      selected_content: orderedExportCategories(categories),
      publication_digest: publication.publication_digest || null,
      source_identity: state.payload.source_identity || null,
      selected_revision_digests: complete.selectedRevisionDigests,
      selected_translation_revision_digests:
        complete.selectedTranslationDigests,
      selected_glossary_revision_digests:
        complete.selectedGlossaryRevisionDigests,
      resources: resources.manifest
    };
    var files = [
      {path: "document.md", bytes: utf8Bytes(complete.markdown)},
      {
        path: "manifest.json",
        bytes: utf8Bytes(JSON.stringify(manifest, null, 2) + "\n")
      }
    ].concat(resources.files);
    return {
      markdown: complete.markdown,
      manifest: manifest,
      archive: buildStoredZip(files)
    };
  }

  function buildPlainMarkdown(scope, selectedCategories) {
    var categories = selectedMarkdownCategories(scope, selectedCategories);
    if (!categories.size) return "";
    var resourcePaths = portableMarkdownResourcePaths(
      state.payload.resources || []
    );
    var complete = scope === "changed" ?
      buildChangedMarkdown(resourcePaths, categories) :
      buildCompleteMarkdown(resourcePaths, categories);
    if (!complete.markdown) return "";
    return stripPortableMarkdownResources(
      degradeLegacyInternalMarkdownLinks(complete.markdown), resourcePaths
    );
  }

  function buildCompleteMarkdown(resourcePaths, selectedCategories) {
    var publication = state.payload.publication;
    var documentValue = publication.source_document;
    var blocks = documentValue.blocks || [];
    var categories = selectedCategories || new Set(["translation"]);
    var sourceSelected = categories.has("source");
    var translationSelected = categories.has("translation");
    var supplementSelected = Array.from(categories).some(function (role) {
      return [
        "source", "translation", "glossary", "references"
      ].indexOf(role) < 0;
    });
    var translations = translationSelected ?
      completeTranslationSelections(blocks) : new Map();
    var noteTranslations = translationSelected ?
      sourceNoteTranslations(documentValue) : new Map();
    var supplements = completeSupplementSelections(categories);
    var selectedTranslationDigests = [];
    var selectedRevisionDigests = [];
    var selectedGlossaryRevisionDigests = [];
    var parts = [];
    var appendedFrontMatter = new Set();
    function appendFrontMatter(blockIndex) {
      if (!sourceSelected && !translationSelected) return;
      sourceFrontMatterEntries(documentValue).filter(function (entry) {
        return entry && entry.kind === "authors" &&
          entry.block_index === blockIndex &&
          !appendedFrontMatter.has(entry.front_matter_id);
      }).forEach(function (entry) {
        pushExportPart(parts, exportSourceFrontMatterMarkdown(entry));
        appendedFrontMatter.add(entry.front_matter_id);
      });
    }
    blocks.forEach(function (block, blockIndex) {
      appendFrontMatter(blockIndex);
      if (sourceSelected || translationSelected) {
        exportDocumentNotesBefore(documentValue, block.block_id).forEach(
          function (note) { parts.push(note); }
        );
      }
      if (isPdfPageMarkerBlock(block) || isStandaloneHtmlCommentBlock(block)) {
        return;
      }
      var translation = translations.get(block.block_id) || null;
      var sourceMarkdown = exportSourceBlockMarkdown(
        block, documentValue, resourcePaths
      );
      sourceMarkdown = exportListOwnedMarkdown(block, sourceMarkdown, false);
      if (sourceSelected) pushExportPart(parts, sourceMarkdown);
      if (translationSelected) {
        if (translation) {
          var translatedMarkdown = exportSelectedRevisionMarkdown(
            block, documentValue, translation, resourcePaths
          );
          if (sourceSelected) {
            if (block.kind === "figure") {
              translatedMarkdown = rewriteMarkdownResourceTargets(
                projectedRevisionMarkdown(translation), resourcePaths
              );
            }
            translatedMarkdown = exportOverlayMarkdown(
              "", translation.title, translatedMarkdown
            );
          }
          translatedMarkdown = exportListOwnedMarkdown(
            block, translatedMarkdown, sourceSelected
          );
          pushExportPart(parts, translatedMarkdown);
          selectedTranslationDigests.push(translation.semantic_digest);
          selectedRevisionDigests.push(translation.semantic_digest);
        } else if (!sourceSelected) {
          pushExportPart(parts, sourceMarkdown);
        }
      } else if (
        !sourceSelected && supplementSelected && block.kind === "heading"
      ) {
        pushExportPart(parts, sourceMarkdown);
      }
      sourceNotesForBlock(documentValue, block.block_id).forEach(function (note) {
        if (sourceSelected) {
          pushExportPart(
            parts, exportSourceNoteMarkdown(note, null, resourcePaths)
          );
        }
        if (translationSelected) {
          var noteTranslation = noteTranslations.get(note.note_id) || null;
          if (noteTranslation) {
            pushExportPart(parts, exportSourceNoteMarkdown(
              note, noteTranslation, resourcePaths
            ));
            selectedTranslationDigests.push(noteTranslation.semantic_digest);
            selectedRevisionDigests.push(noteTranslation.semantic_digest);
          } else if (!sourceSelected) {
            pushExportPart(
              parts, exportSourceNoteMarkdown(note, null, resourcePaths)
            );
          }
        }
      });
      appendFrontMatter(blockIndex + 1);
      (supplements.get(block.block_id) || []).forEach(function (revision) {
        pushExportPart(parts, exportSupplementMarkdown(
          revision,
          rewriteMarkdownResourceTargets(
            normalizeMarkdown(revision.markdown_body), resourcePaths
          )
        ));
        selectedRevisionDigests.push(revision.semantic_digest);
      });
    });
    appendFrontMatter(blocks.length);
    var glossary = categories.has("glossary") ?
      exportGlossaryMarkdown(publication.glossary || [], resourcePaths) : "";
    if (glossary) {
      parts.push(glossary);
      state.glossaryBase.forEach(function (entry) {
        var entryId = glossaryEntryId(entry);
        var revision = state.selectedGlossaryRevisions.get(entryId);
        if (revision) selectedGlossaryRevisionDigests.push(revision.semantic_digest);
      });
    }
    var bibliography = categories.has("references") ?
      exportBibliographyMarkdown(publication.bibliography || []) : "";
    if (bibliography) parts.push(bibliography);
    return {
      markdown: parts.join("\n\n").replace(/\n+$/, "") + "\n",
      selectedTranslationDigests: selectedTranslationDigests,
      selectedRevisionDigests: selectedRevisionDigests,
      selectedGlossaryRevisionDigests: selectedGlossaryRevisionDigests
    };
  }

  function pushExportPart(parts, markdown) {
    markdown = String(markdown || "").replace(/\n+$/, "");
    if (markdown) parts.push(markdown);
  }

  function exportSelectedRevisionMarkdown(
    block, documentValue, revision, resourcePaths
  ) {
    if (block.kind === "figure") {
      return exportFigureMarkdown(block, revision, resourcePaths);
    }
    if (block.kind === "equation") {
      return exportSelectedEquationMarkdown(
        block, documentValue, revision, resourcePaths
      );
    }
    if (block.kind === "code") {
      return exportSelectedCodeMarkdown(block, revision, resourcePaths);
    }
    return rewriteMarkdownResourceTargets(
      projectedRevisionMarkdown(revision), resourcePaths
    );
  }

  function projectedRevisionMarkdown(revision) {
    return projectGlossaryMarkdown(revision.markdown_body, revision);
  }

  function exportOverlayMarkdown(role, title, markdown) {
    var label = [role, title].filter(Boolean).map(function (value) {
      return escapeMarkdownStrong(String(value).replace(/\s+/g, " ").trim());
    }).join(" · ");
    markdown = String(markdown || "").replace(/\n+$/, "");
    if (!markdown) return "";
    return label ? "**" + label + "**\n\n" + markdown : markdown;
  }

  function exportSupplementMarkdown(revision, markdown) {
    if (["guide", "companion", "note"].indexOf(revision.role) < 0) {
      return exportOverlayMarkdown(
        roleLabel(revision.role), revision.title, markdown
      );
    }
    var label = [roleLabel(revision.role), revision.title].filter(Boolean).map(
      function (value) {
        return escapeMarkdownStrong(
          String(value).replace(/\s+/g, " ").trim()
        );
      }
    ).join(" · ");
    markdown = canonicalizeLegacyDisplayMath(
      String(markdown || "")
    ).replace(/\n+$/, "");
    if (!markdown) return "";
    return ["**" + label + "**", ""].concat(markdown.split("\n")).map(
      function (line) { return line ? "> " + line : ">"; }
    ).join("\n");
  }

  function completeSupplementSelections(categories) {
    var selected = new Map();
    selectedForMarkdown("all").forEach(function (revision) {
      if (
        !categories.has(revision.role) ||
        revision.role === "translation" || revision.role === "source"
      ) {
        return;
      }
      var target = fragmentTargetId(revision);
      if (!target) return;
      var values = selected.get(target) || [];
      values.push(revision);
      selected.set(target, values);
    });
    selected.forEach(function (values) {
      values.sort(function (left, right) {
        return left.priority - right.priority ||
          comparePortableText(left.fragment_id, right.fragment_id);
      });
    });
    return selected;
  }

  function buildChangedMarkdown(resourcePaths, categories) {
    var documentValue = state.payload.publication.source_document;
    var blocks = documentValue.blocks || [];
    var blockById = new Map(blocks.map(function (block) {
      return [block.block_id, block];
    }));
    var blockOrder = new Map(blocks.map(function (block, index) {
      return [block.block_id, index];
    }));
    var changedValues = selectedForMarkdown("changed");
    var changedNoteTranslations = categories.has("translation") ?
      sourceNoteTranslations(documentValue, changedValues) : new Map();
    var revisions = changedValues.filter(function (revision) {
      return categories.has(revision.role) && revision.role !== "source" &&
        !sourceNoteTranslationId(documentValue, revision);
    });
    revisions.sort(function (left, right) {
      var leftTarget = fragmentTargetId(left);
      var rightTarget = fragmentTargetId(right);
      var leftOrder = blockOrder.has(leftTarget) ? blockOrder.get(leftTarget) : Infinity;
      var rightOrder = blockOrder.has(rightTarget) ? blockOrder.get(rightTarget) : Infinity;
      return leftOrder - rightOrder || left.priority - right.priority ||
        comparePortableText(left.fragment_id, right.fragment_id);
    });
    var glossaryChanges = categories.has("glossary") ? changedGlossaryEntries() : [];
    if (
      !revisions.length && !changedNoteTranslations.size &&
      !glossaryChanges.length
    ) {
      return {
        markdown: "",
        selectedTranslationDigests: [],
        selectedRevisionDigests: [],
        selectedGlossaryRevisionDigests: []
      };
    }
    var parts = [
      "# " + markdownHeading(readerTitle() + " — " + labels().changedContent)
    ];
    var selectedTranslationDigests = [];
    var selectedRevisionDigests = [];
    var selectedGlossaryRevisionDigests = [];
    revisions.forEach(function (revision) {
      var block = blockById.get(fragmentTargetId(revision));
      var markdown = block && revision.role === "translation" ?
        exportSelectedRevisionMarkdown(
          block, documentValue, revision, resourcePaths
        ) : rewriteMarkdownResourceTargets(
          normalizeMarkdown(revision.markdown_body), resourcePaths
        );
      if (["guide", "companion", "note"].indexOf(revision.role) >= 0) {
        pushExportPart(parts, exportSupplementMarkdown(revision, markdown));
      } else {
        var heading = revision.role === "translation" ? revision.title :
          roleLabel(revision.role) +
            (revision.title ? " · " + revision.title : "");
        if (heading) parts.push("## " + markdownHeading(heading));
        pushExportPart(parts, markdown);
      }
      selectedRevisionDigests.push(revision.semantic_digest);
      if (revision.role === "translation") {
        selectedTranslationDigests.push(revision.semantic_digest);
      }
    });
    sourceNotes(documentValue).forEach(function (note) {
      var translation = changedNoteTranslations.get(note.note_id);
      if (!translation) return;
      pushExportPart(
        parts, exportSourceNoteMarkdown(note, translation, resourcePaths)
      );
      selectedRevisionDigests.push(translation.semantic_digest);
      selectedTranslationDigests.push(translation.semantic_digest);
    });
    if (glossaryChanges.length) {
      pushExportPart(parts, exportGlossaryMarkdown(
        glossaryChanges.map(function (item) { return item.entry; }),
        resourcePaths
      ));
      glossaryChanges.forEach(function (item) {
        selectedGlossaryRevisionDigests.push(item.digest);
      });
    }
    return {
      markdown: parts.join("\n\n").replace(/\n+$/, "") + "\n",
      selectedTranslationDigests: selectedTranslationDigests,
      selectedRevisionDigests: selectedRevisionDigests,
      selectedGlossaryRevisionDigests: selectedGlossaryRevisionDigests
    };
  }

  function completeTranslationSelections(blocks) {
    var documentValue = state.payload.publication.source_document;
    var blockIds = new Set(blocks.map(function (block) {
      return block.block_id;
    }));
    var candidates = new Map();
    state.selected.forEach(function (revision) {
      var anchor = revision && revision.anchor || {};
      var related = anchor.related_blocks;
      if (
        !fragmentIsVisible(revision) ||
        sourceNoteTranslationId(documentValue, revision) ||
        revision.role !== "translation" ||
        anchor.kind !== "block" ||
        !blockIds.has(anchor.target_id) ||
        !Array.isArray(related) || related.length !== 1 ||
        related[0].block_id !== anchor.target_id ||
        !normalizeMarkdown(revision.markdown_body).trim()
      ) {
        return;
      }
      var values = candidates.get(anchor.target_id) || [];
      values.push(revision);
      candidates.set(anchor.target_id, values);
    });
    var selected = new Map();
    candidates.forEach(function (values, blockId) {
      values.sort(function (left, right) {
        return left.priority - right.priority ||
          comparePortableText(left.fragment_id, right.fragment_id);
      });
      selected.set(blockId, values[0]);
    });
    return selected;
  }

  function exportSourceFrontMatterMarkdown(entry) {
    var authors = (entry.authors || []).map(function (author) {
      var value = escapeMarkdownStrong(String(author.name || ""));
      var markers = (author.markers || []).map(String).join(",");
      if (markers) value += " [" + markers + "]";
      var details = [];
      if (author.orcid_url) {
        details.push("[" + labels().orcid + "](" +
          markdownLinkDestination(author.orcid_url) + ")");
      }
      (author.contacts || []).forEach(function (contact) {
        var visible = escapeMarkdownLinkLabel(String(contact.value || ""));
        details.push(contact.target ?
          "[" + visible + "](" + markdownLinkDestination(contact.target) + ")" :
          visible);
      });
      return value + (details.length ? " (" + details.join("; ") + ")" : "");
    });
    var lines = ["**" + labels().authors + ":** " + authors.join("; ")];
    if ((entry.affiliations || []).length) {
      lines.push("", "**" + labels().affiliations + ":**");
      (entry.affiliations || []).forEach(function (affiliation) {
        lines.push(
          "- [" + escapeMarkdownInlineText(String(affiliation.marker || "")) +
          "] " + escapeMarkdownInlineText(String(affiliation.text || ""))
        );
      });
    }
    return lines.join("\n") + "\n";
  }

  function exportSourceNoteMarkdown(note, translation, resourcePaths) {
    var body = translation ? rewriteMarkdownResourceTargets(
      projectedRevisionMarkdown(translation), resourcePaths
    ) : exportInlineSpansMarkdown(
      note.inline_spans, note.body, resourcePaths
    );
    body = String(body || "").replace(/\n+$/, "");
    if (!body) return "";
    var label = (translation ? labels().translation + " · " : "") +
      labels().sourceNote + " " + String(note.marker || "");
    return ["**" + escapeMarkdownStrong(label) + "**", ""].concat(
      body.split("\n")
    ).map(function (line) { return line ? "> " + line : ">"; }).join("\n") + "\n";
  }

  function exportDocumentNotesBefore(documentValue, blockId) {
    var notes = (documentValue.metadata || {}).document_notes || {};
    if (
      notes.schema_version !== "ac.document.document_notes.v1" ||
      !Array.isArray(notes.items)
    ) {
      return [];
    }
    return notes.items.filter(function (item) {
      return item && item.kind === "metadata" &&
        item.before_block_id === blockId && String(item.text || "").trim();
    }).map(function (item) {
      return normalizeMarkdown(String(item.text)).replace(/\n/g, "\n> ")
        .replace(/^/, "> ");
    });
  }

  function exportSourceBlockMarkdown(block, documentValue, resourcePaths) {
    var payload = block.payload || {};
    if (block.kind === "heading") {
      var headingPresentation = sourcePresentationBlock(
        documentValue, block.block_id
      );
      var headingView = sourcePresentationField(
        documentValue, block.block_id, "text", null, null, null
      );
      var headingText = headingView ?
        exportPresentationFieldMarkdown(headingView, resourcePaths) :
        rewriteMarkdownResourceTargets(String(payload.text || ""), resourcePaths);
      if (
        headingPresentation &&
        headingPresentation.roles.indexOf("classification") >= 0
      ) return "**" + headingText + "**\n";
      var level = Math.max(1, Math.min(6, Number(payload.level) || 1));
      return "#".repeat(level) + " " + headingText + "\n";
    }
    if (block.kind === "paragraph") {
      var paragraphView = sourcePresentationField(
        documentValue, block.block_id, "text", null, null, null
      );
      return (paragraphView ?
        exportPresentationFieldMarkdown(paragraphView, resourcePaths) :
        exportInlineSpansMarkdown(
          payload.inline_spans, payload.text, resourcePaths
        )) + "\n";
    }
    if (block.kind === "list") {
      if (listPathEntries(block).length) {
        var ownedItem = (payload.items || [])[0] || {};
        var ownedView = sourcePresentationField(
          documentValue, block.block_id, "list_item", 0, null, null
        );
        return (ownedView ?
          exportPresentationFieldMarkdown(ownedView, resourcePaths) :
          exportInlineSpansMarkdown(
            ownedItem.inline_spans, ownedItem.text, resourcePaths
          )) + "\n";
      }
      return (payload.items || []).map(function (item, index) {
        var prefix = payload.ordered ? String(index + 1) + ". " : "- ";
        var itemView = sourcePresentationField(
          documentValue, block.block_id, "list_item", index, null, null
        );
        var content = (itemView ?
          exportPresentationFieldMarkdown(itemView, resourcePaths) :
          exportInlineSpansMarkdown(
            item.inline_spans, item.text, resourcePaths
          )).replace(/\n/g, "\n" + " ".repeat(prefix.length));
        return prefix + content;
      }).join("\n") + "\n";
    }
    if (block.kind === "code") {
      var code = normalizeMarkdown(String(payload.text || ""));
      var fence = "`".repeat(Math.max(3, longestRun(code, "`") + 1));
      var language = String(payload.language || "").trim()
        .replace(/[`\r\n]/g, "");
      return fence + language + "\n" + code +
        (code.endsWith("\n") ? "" : "\n") + fence + "\n";
    }
    if (block.kind === "equation") {
      var equation = "$$\n" + String(payload.tex || "").trim() + "\n$$";
      var equationLabel = exportEquationLabel(block, documentValue);
      return equation + (equationLabel ?
        "\n\nEquation label: " + displayEquationLabel(equationLabel) : "") + "\n";
    }
    if (block.kind === "table") {
      return exportSourceTableMarkdown(
        block, documentValue, payload, resourcePaths
      );
    }
    if (block.kind === "figure") {
      return exportFigureMarkdown(block, null, resourcePaths);
    }
    throw new Error("unsupported RichDocument block kind: " + block.kind);
  }

  function exportInlineSpansMarkdown(spans, fallback, resourcePaths) {
    if (!Array.isArray(spans) || !spans.length) {
      return rewriteMarkdownResourceTargets(
        normalizeMarkdown(String(fallback || "")), resourcePaths
      );
    }
    return spans.map(function (span) {
      if (span.kind === "math") {
        var tex = String(span.tex || span.source || "");
        return containsUnescapedDollar(tex) ? "\\(" + tex + "\\)" :
          "$" + tex + "$";
      }
      if (span.kind === "link") {
        var target = portableResourceTarget(
          String(span.target || ""), resourcePaths
        );
        return "[" + escapeMarkdownLinkLabel(
          String(span.text || span.target || "")
        ) + "](" + markdownLinkDestination(target) + ")";
      }
      return escapeMarkdownInlineText(String(span.text || ""));
    }).join("");
  }

  function exportPresentationFieldMarkdown(view, resourcePaths) {
    var marks = view.marks || [];
    return (view.inline_spans || []).map(function (span) {
      var boundaries = new Set([span.start, span.end]);
      marks.forEach(function (mark) {
        if (mark.start > span.start && mark.start < span.end) {
          boundaries.add(mark.start);
        }
        if (mark.end > span.start && mark.end < span.end) {
          boundaries.add(mark.end);
        }
      });
      var points = Array.from(boundaries).sort(function (left, right) {
        return left - right;
      });
      return points.slice(0, -1).map(function (start, index) {
        var end = points[index + 1];
        var content = exportPresentationSpanSlice(
          span, start - span.start, end - span.start, resourcePaths
        );
        var active = marks.filter(function (mark) {
          return mark.start <= start && mark.end >= end;
        }).sort(function (left, right) {
          return left.start - right.start || right.end - left.end ||
            (left.kind === "strong" ? -1 : 1);
        });
        active.slice().reverse().forEach(function (mark) {
          var token = mark.kind === "strong" ? "**" : "*";
          content = token + content + token;
        });
        return content;
      }).join("");
    }).join("");
  }

  function exportPresentationSpanSlice(span, start, end, resourcePaths) {
    var text = Array.from(String(span.text || "")).slice(start, end).join("");
    if (span.kind === "math") {
      if (start !== 0 || end !== Array.from(span.text || "").length) {
        throw new Error("source presentation mark splits an inline math span");
      }
      var tex = String(span.tex || span.source || "");
      return containsUnescapedDollar(tex) ? "\\(" + tex + "\\)" :
        "$" + tex + "$";
    }
    if (span.kind === "link") {
      var target = portableResourceTarget(
        String(span.target || ""), resourcePaths
      );
      return "[" + escapeMarkdownLinkLabel(text || span.target || "") + "](" +
        markdownLinkDestination(target) + ")";
    }
    return escapeMarkdownInlineText(text);
  }

  function exportEquationLabel(block, documentValue) {
    var reconciliation = (
      (documentValue.metadata || {}).equation_label_reconciliation || {}
    )[block.block_id];
    if (
      reconciliation &&
      typeof reconciliation.effective_label === "string" &&
      reconciliation.effective_label.trim()
    ) {
      return reconciliation.effective_label.trim();
    }
    return String((block.payload || {}).label || "").trim();
  }

  function exportSelectedEquationMarkdown(
    block, documentValue, translation, resourcePaths
  ) {
    var markdown = rewriteMarkdownResourceTargets(
      projectedRevisionMarkdown(translation), resourcePaths
    ).replace(/\n+$/, "");
    var label = exportEquationLabel(block, documentValue);
    var labelLine = label ?
      "Equation label: " + displayEquationLabel(label) : "";
    if (labelLine && !markdown.endsWith(labelLine)) {
      markdown += "\n\n" + labelLine;
    }
    return markdown + "\n";
  }

  function exportSelectedCodeMarkdown(block, translation, resourcePaths) {
    var markdown = rewriteMarkdownResourceTargets(
      projectedRevisionMarkdown(translation), resourcePaths
    ).replace(/\n+$/, "");
    var language = String((block.payload || {}).language || "").trim()
      .replace(/[`\r\n]/g, "");
    var lines = markdown.split("\n");
    var opening = /^(`{3,}|~{3,})(.*)$/.exec(lines[0] || "");
    if (language && opening && !opening[2].trim()) {
      lines[0] = opening[1] + language;
    }
    return lines.join("\n") + "\n";
  }

  function exportSourceTableMarkdown(
    block, documentValue, payload, resourcePaths
  ) {
    var headers = Array.isArray(payload.headers) ? payload.headers : [];
    var rows = Array.isArray(payload.rows) ? payload.rows : [];
    var width = headers.length || (rows[0] || []).length;
    var lines = [];
    if (width) {
      var normalizedHeaders = headers.length ? headers : Array(width).fill("");
      lines.push("| " + normalizedHeaders.map(function (value, columnIndex) {
        var view = headers.length ? sourcePresentationField(
          documentValue, block.block_id, "table_header", null, null,
          columnIndex
        ) : null;
        return view ? exportPresentationTableCell(view, resourcePaths) :
          exportTableCell(value, resourcePaths);
      }).join(" | ") + " |");
      lines.push("| " + Array(width).fill("---").join(" | ") + " |");
      rows.forEach(function (row, rowIndex) {
        lines.push("| " + row.map(function (value, columnIndex) {
          var view = sourcePresentationField(
            documentValue, block.block_id, "table_cell", null, rowIndex,
            columnIndex
          );
          return view ? exportPresentationTableCell(view, resourcePaths) :
            exportTableCell(value, resourcePaths);
        }).join(" | ") + " |");
      });
    }
    var captionView = sourcePresentationField(
      documentValue, block.block_id, "caption", null, null, null
    );
    var caption = captionView ?
      exportPresentationFieldMarkdown(captionView, resourcePaths) :
      rewriteMarkdownResourceTargets(
        String(payload.caption || "").trim(), resourcePaths
      );
    var captionPresentation = sourceCaptionPresentation(
      documentValue, block.block_id
    );
    if (caption && captionPresentation &&
      captionPresentation.placement === "before_content") {
      lines.unshift("", "Table: " + caption, "");
    } else if (caption) {
      lines.push("", "Table: " + caption);
    }
    return (lines.join("\n") || "[Empty table]") + "\n";
  }

  function exportPresentationTableCell(view, resourcePaths) {
    return exportPresentationFieldMarkdown(view, resourcePaths)
      .replace(/\|/g, "\\|")
      .replace(/\r?\n/g, "<br>");
  }

  function exportTableCell(value, resourcePaths) {
    return rewriteMarkdownResourceTargets(String(value), resourcePaths)
      .replace(/\\/g, "\\\\")
      .replace(/\|/g, "\\|")
      .replace(/\r?\n/g, "<br>");
  }

  function exportFigureMarkdown(block, translation, resourcePaths) {
    var payload = block.payload || {};
    var parts = [];
    var panels = sourceFigurePanels(block);
    if (panels.length) {
      panels.filter(function (panel) {
        return panel.status === "available";
      }).forEach(function (panel) {
        var panelDigest = String(panel.asset_digest || "");
        var panelPath = portableResourceTarget(panelDigest, resourcePaths);
        var panelAlt = escapeMarkdownLinkLabel(String(
          panel.alt_text || payload.alt_text || panel.logical_name || ""
        ));
        if (panelPath && panelPath !== panelDigest) {
          parts.push(
            "![" + panelAlt + "](" + markdownLinkDestination(panelPath) + ")"
          );
        }
      });
    } else {
      var resourcePath = portableResourceTarget(
        String(payload.asset_digest || ""), resourcePaths
      );
      var alt = escapeMarkdownLinkLabel(String(payload.alt_text || ""));
      if (resourcePath && resourcePath !== String(payload.asset_digest || "")) {
        parts.push(
          "![" + alt + "](" + markdownLinkDestination(resourcePath) + ")"
        );
      } else {
        var description = String(
          payload.alt_text || payload.caption || payload.logical_name || ""
        ).trim();
        if (description) parts.push("[Figure: " + description + "]");
      }
    }
    var captionView = !translation ? sourcePresentationField(
      state.payload.publication.source_document,
      block.block_id, "caption", null, null, null
    ) : null;
    var caption = translation ?
      projectedRevisionMarkdown(translation).replace(/\n+$/, "") :
      captionView ? exportPresentationFieldMarkdown(
        captionView, resourcePaths
      ) : String(payload.caption || "").trim();
    caption = rewriteMarkdownResourceTargets(caption, resourcePaths);
    if (caption) parts.push(caption);
    return parts.join("\n\n") + "\n";
  }

  function exportGlossaryMarkdown(glossary, resourcePaths) {
    if (!glossary.length) return "";
    var lines = ["## " + markdownHeading(labels().glossary)];
    glossary.forEach(function (entry) {
      var source = String(entry.term || entry.source_term || "").trim();
      var translated = String(
        entry.translated_term || entry.translation || ""
      ).trim();
      var rawDefinition = entry.definition || "";
      var definition = canonicalizeLegacyDisplayMath(
        glossaryDefinitionHasForbiddenControl(rawDefinition) ?
          recoverLegacyGlossaryDefinition(rawDefinition) : rawDefinition
      ).trim();
      definition = rewriteMarkdownResourceTargets(definition, resourcePaths);
      var title = [source, translated].filter(Boolean).filter(function (
        value, index, values
      ) {
        return values.indexOf(value) === index;
      }).join(" / ");
      if (!title && !definition) {
        lines.push("- " + markdownInlineCode(stableStringify(entry)));
        return;
      }
      lines.push(
        "- " + (title ? "**" + escapeMarkdownStrong(title) + "**" : "")
      );
      if (!definition) return;
      lines.push("");
      definition.split("\n").forEach(function (line) {
        lines.push("  " + line);
      });
    });
    return lines.join("\n");
  }

  function exportBibliographyMarkdown(bibliography) {
    if (!bibliography.length) return "";
    var groups = [];
    var byIdentity = new Map();
    bibliography.forEach(function (entry, entryIndex) {
      var id = entry.evidence_id || entry.citation_id || entry.id || "";
      var dois = Array.isArray(entry.dois) ? entry.dois : [];
      var arxivIds = Array.isArray(entry.arxiv_ids) ? entry.arxiv_ids : [];
      var visible = id || entry.title || entry.source || entry.url ||
        dois.length || arxivIds.length;
      var identity;
      if (!visible) {
        identity = "unknown:" + entryIndex + ":" + stableStringify(entry);
      } else {
        identity = bibliographyIdentity(entry);
        if (identity === "id:" && !id && entry.title) {
          identity = "entry:" + entryIndex + ":" + stableStringify(entry);
        }
      }
      var group = byIdentity.get(identity);
      if (!group) {
        group = {
          entry: entry,
          ids: [],
          dois: [],
          arxivIds: [],
          unknown: !visible
        };
        byIdentity.set(identity, group);
        groups.push(group);
      }
      if (id && group.ids.indexOf(id) < 0) group.ids.push(String(id));
      dois.forEach(function (doi) {
        var value = String(doi);
        if (group.dois.indexOf(value) < 0) group.dois.push(value);
      });
      arxivIds.forEach(function (identifier) {
        var value = String(identifier);
        if (group.arxivIds.indexOf(value) < 0) group.arxivIds.push(value);
      });
    });
    var lines = ["## " + markdownHeading(labels().references)];
    groups.forEach(function (group, index) {
      var entry = group.entry;
      if (group.unknown) {
        lines.push(
          String(index + 1) + ". " +
          markdownInlineCode(stableStringify(entry))
        );
        return;
      }
      var title = String(entry.title || entry.source || entry.url || "").trim();
      var source = String(entry.source || entry.url || "").trim();
      var markers = group.ids.map(function (id) { return "[@" + id + "]"; })
        .join(", ");
      var content = "";
      if (/^https?:\/\//i.test(source)) {
        content = "[" + escapeMarkdownLinkLabel(title || source) + "](" +
          markdownLinkDestination(source) + ")";
      } else {
        content = title ? "**" + escapeMarkdownStrong(title) + "**" : "";
        if (source && source !== title) content += " — " + source;
      }
      var details = [];
      group.dois.forEach(function (doi) {
        details.push("DOI: " + String(doi));
      });
      group.arxivIds.forEach(function (identifier) {
        details.push("arXiv: " + String(identifier));
      });
      lines.push(
        String(index + 1) + ". " + [markers, content].filter(Boolean).join(" ") +
        (details.length ? " — " + details.join("; ") : "")
      );
    });
    return lines.join("\n");
  }

  function escapeMarkdownInlineText(value) {
    return String(value).replace(/([\\`*_[\]<>])/g, "\\$1");
  }

  function escapeMarkdownLinkLabel(value) {
    return String(value).replace(/([\\\]])/g, "\\$1").replace(/\r?\n/g, " ");
  }

  function escapeMarkdownStrong(value) {
    return String(value).replace(/([\\*_])/g, "\\$1").replace(/\r?\n/g, " ");
  }

  function markdownInlineCode(value) {
    var text = String(value);
    var fence = "`".repeat(Math.max(1, longestRun(text, "`") + 1));
    return fence + (text.startsWith("`") || text.endsWith("`") ?
      " " + text + " " : text) + fence;
  }

  function markdownLinkDestination(value) {
    var target = String(value || "");
    return /[\s()<>]/.test(target) ?
      "<" + target.replace(/>/g, "%3E") + ">" : target;
  }

  function containsUnescapedDollar(value) {
    var text = String(value);
    for (var index = 0; index < text.length; index += 1) {
      if (text.charAt(index) !== "$") continue;
      var slashes = 0;
      for (
        var cursor = index - 1;
        cursor >= 0 && text.charAt(cursor) === "\\";
        cursor -= 1
      ) {
        slashes += 1;
      }
      if (slashes % 2 === 0) return true;
    }
    return false;
  }

  function longestRun(value, character) {
    var longest = 0;
    var current = 0;
    String(value).split("").forEach(function (item) {
      current = item === character ? current + 1 : 0;
      longest = Math.max(longest, current);
    });
    return longest;
  }

  function comparePortableText(left, right) {
    var leftText = String(left);
    var rightText = String(right);
    return leftText < rightText ? -1 : leftText > rightText ? 1 : 0;
  }

  function portableMarkdownResourceIdentity(resource) {
    var digest = String(
      resource.artifact_digest || resource.digest || ""
    ).toLowerCase();
    var logicalName = String(resource.logical_name || "");
    var mediaType = String(resource.media_type || "").toLowerCase();
    if (!/^[0-9a-f]{64}$/.test(digest)) {
      throw new Error("Markdown export resource digest is invalid");
    }
    if (!logicalName || !mediaType) {
      throw new Error("Markdown export resource metadata is incomplete");
    }
    return {
      digest: digest,
      logicalName: logicalName,
      mediaType: mediaType,
      path: "resources/" + digest + "/" +
        portableResourceBasename(logicalName)
    };
  }

  function portableMarkdownResourcePaths(resources) {
    return portableMarkdownPathByAlias(resources.map(
      portableMarkdownResourceIdentity
    ));
  }

  function portableMarkdownPathByAlias(values) {
    var pathByAlias = new Map();
    values.forEach(function (item) {
      [item.digest, item.logicalName].forEach(function (alias) {
        var existing = pathByAlias.get(alias);
        if (existing && existing !== item.path) {
          throw new Error("Markdown export resource alias is ambiguous");
        }
        pathByAlias.set(alias, item.path);
      });
      var slashName = item.logicalName.replace(/\\/g, "/");
      if (!pathByAlias.has(slashName)) {
        pathByAlias.set(slashName, item.path);
      }
      try {
        var encoded = encodeURI(item.logicalName);
        if (!pathByAlias.has(encoded)) pathByAlias.set(encoded, item.path);
      } catch (_error) {
        /* The exact validated logical name remains available as an alias. */
      }
    });
    return pathByAlias;
  }

  function portableMarkdownResources(resources, includedPaths) {
    var values = resources.map(function (resource) {
      return {
        identity: portableMarkdownResourceIdentity(resource),
        resource: resource
      };
    }).filter(function (value) {
      return !includedPaths || includedPaths.has(value.identity.path);
    }).map(function (value) {
      var identity = value.identity;
      var resource = hydrateResource(value.resource);
      var bytes = dataUriBytes(resource.data_uri, identity.mediaType);
      if (
        Number.isInteger(resource.size) && resource.size >= 0 &&
        bytes.length !== resource.size
      ) {
        throw new Error("Markdown export resource size does not match metadata");
      }
      return {
        digest: identity.digest,
        logicalName: identity.logicalName,
        mediaType: identity.mediaType,
        size: bytes.length,
        path: identity.path,
        bytes: bytes
      };
    }).sort(function (left, right) {
      return comparePortableText(left.path, right.path);
    });
    return {
      files: values.map(function (item) {
        return {path: item.path, bytes: item.bytes};
      }),
      manifest: values.map(function (item) {
        return {
          artifact_digest: item.digest,
          media_type: item.mediaType,
          logical_name: item.logicalName,
          size: item.size,
          path: item.path
        };
      })
    };
  }

  function portableResourceBasename(logicalName) {
    var normalized = String(logicalName).normalize("NFC").replace(/\\/g, "/");
    var name = normalized.split("/").filter(Boolean).pop() || "resource";
    name = name.replace(/[\u0000-\u001f<>:"/\\|?*#%()[\]{}]/g, "-")
      .replace(/\s+/g, "-")
      .replace(/^[. -]+|[. ]+$/g, "");
    if (!name) name = "resource";
    var characters = Array.from(name);
    if (characters.length > 160) name = characters.slice(-160).join("");
    return name;
  }

  function dataUriBytes(value, expectedMediaType) {
    var uri = String(value || "");
    var comma = uri.indexOf(",");
    if (comma < 0 || uri.slice(0, 5).toLowerCase() !== "data:") {
      throw new Error("Markdown export resource data URI is missing");
    }
    var header = uri.slice(5, comma);
    var parts = header.split(";");
    if (
      String(parts.shift() || "").toLowerCase() !== expectedMediaType ||
      !parts.some(function (part) { return part.toLowerCase() === "base64"; })
    ) {
      throw new Error("Markdown export resource data URI is invalid");
    }
    var decoded;
    try {
      decoded = atob(uri.slice(comma + 1));
    } catch (error) {
      throw new Error("Markdown export resource base64 is invalid");
    }
    var bytes = new Uint8Array(decoded.length);
    for (var index = 0; index < decoded.length; index += 1) {
      bytes[index] = decoded.charCodeAt(index);
    }
    return bytes;
  }

  function portableResourceTarget(target, resourcePaths) {
    var value = String(target || "");
    if (/^(?:[#/?]|[A-Za-z][A-Za-z0-9+.-]*:)/.test(value)) return value;
    var direct = resourcePaths.get(value);
    if (direct) return direct;
    if (value.slice(0, 2) === "./" && resourcePaths.has(value.slice(2))) {
      return resourcePaths.get(value.slice(2));
    }
    try {
      var decoded = decodeURIComponent(value);
      if (resourcePaths.has(decoded)) return resourcePaths.get(decoded);
    } catch (_error) {
      /* Preserve malformed or non-URL resource spelling verbatim. */
    }
    return value;
  }

  function rewriteMarkdownResourceTargets(markdown, resourcePaths) {
    var normalized = normalizeMarkdown(String(markdown || ""));
    var codeLines = markdownCodeLineIndexes(normalized);
    return normalized.split("\n").map(
      function (line, lineNumber) {
        if (codeLines.has(lineNumber)) return line;
        return rewriteMarkdownHtmlTargets(rewriteMarkdownInlineTargets(
          rewriteMarkdownReferenceTarget(line, resourcePaths),
          resourcePaths
        ), resourcePaths);
      }
    ).join("\n");
  }

  function rewriteMarkdownHtmlTargets(line, resourcePaths) {
    return mapMarkdownOutsideCodeSpans(line, function (segment) {
      return transformMarkdownHtmlTags(segment, function (tag) {
        return tag.replace(
          /\b(src|href)(\s*=\s*)(?:"([^"]*)"|'([^']*)'|([^\s>]+))/gi,
          function (_match, name, separator, doubleQuoted, singleQuoted, bare) {
            var target = doubleQuoted !== undefined ? doubleQuoted :
              singleQuoted !== undefined ? singleQuoted : bare;
            var replacement = portableResourceTarget(target, resourcePaths);
            if (replacement === target) return _match;
            if (doubleQuoted !== undefined) {
              return name + separator + '"' + replacement + '"';
            }
            if (singleQuoted !== undefined) {
              return name + separator + "'" + replacement + "'";
            }
            return name + separator + replacement;
          }
        );
      });
    });
  }

  function mapMarkdownOutsideCodeSpans(line, transform) {
    var value = String(line);
    var output = "";
    var position = 0;
    var plainStart = 0;
    while (position < value.length) {
      if (value.charAt(position) !== "`") {
        position += 1;
        continue;
      }
      var run = 1;
      while (value.charAt(position + run) === "`") run += 1;
      var codeEnd = markdownCodeSpanEnd(value, position + run, run);
      if (codeEnd < 0) return output + transform(value.slice(plainStart));
      output += transform(value.slice(plainStart, position));
      output += value.slice(position, codeEnd + run);
      position = codeEnd + run;
      plainStart = position;
    }
    return output + transform(value.slice(plainStart));
  }

  function transformMarkdownHtmlTags(value, transform) {
    var text = String(value);
    var output = "";
    var position = 0;
    var tagStart = /<[A-Za-z][A-Za-z0-9:-]*(?=[\s/>])/g;
    while (position < text.length) {
      tagStart.lastIndex = position;
      var match = tagStart.exec(text);
      if (!match) return output + text.slice(position);
      output += text.slice(position, match.index);
      var quote = null;
      var end = -1;
      for (var index = tagStart.lastIndex; index < text.length; index += 1) {
        var character = text.charAt(index);
        if (quote) {
          if (character === quote) quote = null;
        } else if (character === '"' || character === "'") {
          quote = character;
        } else if (character === ">") {
          end = index;
          break;
        }
      }
      if (end < 0) return output + text.slice(match.index);
      output += transform(text.slice(match.index, end + 1), match.index);
      position = end + 1;
    }
    return output;
  }

  function markdownHtmlResourceTargets(tag) {
    var targets = [];
    var attribute = /\b(?:src|href)\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s>]+))/gi;
    var match;
    while ((match = attribute.exec(String(tag)))) {
      targets.push(
        match[1] !== undefined ? match[1] :
          match[2] !== undefined ? match[2] : match[3] || ""
      );
    }
    return targets;
  }

  function markdownCodeLineIndexes(markdown, parsedTokens) {
    if (!state.md || typeof state.md.parse !== "function") {
      throw new Error("Markdown parser is required for export");
    }
    var lines = new Set();
    (parsedTokens || state.md.parse(
      normalizeMarkdown(String(markdown || "")), {}
    )).forEach(
      function (token) {
        if (
          ["fence", "code_block"].indexOf(token.type) < 0 ||
          !Array.isArray(token.map)
        ) return;
        for (var index = token.map[0]; index < token.map[1]; index += 1) {
          lines.add(index);
        }
      }
    );
    return lines;
  }

  function degradeLegacyInternalMarkdownLinks(markdown) {
    return degradeLegacyMarkdownLinks(markdown, legacyInternalMarkdownTarget);
  }

  function degradeLegacyBibliographyMarkdownLinks(markdown) {
    return degradeLegacyMarkdownLinks(markdown, legacyBibliographyTarget);
  }

  function degradeLegacyMarkdownLinks(markdown, targetTest) {
    var normalized = normalizeMarkdown(String(markdown || ""));
    var tokens = state.md.parse(normalized, {});
    var codeLines = markdownCodeLineIndexes(normalized, tokens);
    var lines = normalized.split("\n");
    var references = legacyInternalMarkdownReferences(
      lines, codeLines, targetTest
    );
    lines = lines.map(function (line, lineNumber) {
      if (references.definitionLines.has(lineNumber)) {
        var quote = /^((?: {0,3}> ?)*)/.exec(line);
        return quote ? quote[1].replace(/[ \t]+$/, "") : "";
      }
      return line;
    });
    var output = [];
    var lineNumber = 0;
    markdownInlineLineRanges(tokens).forEach(function (range) {
      if (lineNumber < range.start) {
        output.push(lines.slice(lineNumber, range.start).join("\n"));
      }
      output.push(degradeLegacyInternalMarkdownChunk(
        lines.slice(range.start, range.end).join("\n"), references.aliases,
        targetTest
      ));
      lineNumber = range.end;
    });
    if (lineNumber < lines.length) {
      output.push(lines.slice(lineNumber).join("\n"));
    }
    return output.join("\n");
  }

  function markdownInlineLineRanges(tokens) {
    var ranges = tokens.filter(function (token) {
      return token.type === "inline" && Array.isArray(token.map) &&
        nonnegativeInteger(token.map[0]) &&
        nonnegativeInteger(token.map[1]) && token.map[0] < token.map[1];
    }).map(function (token) {
      return {start: token.map[0], end: token.map[1]};
    }).sort(function (left, right) {
      return left.start - right.start || left.end - right.end;
    });
    return ranges.reduce(function (merged, range) {
      var previous = merged[merged.length - 1];
      if (previous && range.start < previous.end) {
        previous.end = Math.max(previous.end, range.end);
      } else {
        merged.push(range);
      }
      return merged;
    }, []);
  }

  function degradeLegacyInternalMarkdownChunk(
    value, referenceAliases, targetTest
  ) {
    targetTest = targetTest || legacyInternalMarkdownTarget;
    var output = "";
    var position = 0;
    while (position < value.length) {
      if (value.charAt(position) === "`") {
        var run = 1;
        while (value.charAt(position + run) === "`") run += 1;
        var codeEnd = markdownCodeSpanEnd(value, position + run, run);
        if (codeEnd < 0) {
          output += value.slice(position, position + run);
          position += run;
          continue;
        }
        output += value.slice(position, codeEnd + run);
        position = codeEnd + run;
        continue;
      }
      var isImage = value.slice(position, position + 2) === "![";
      var bracket = isImage ? position + 1 :
        value.charAt(position) === "[" ? position : -1;
      if (bracket >= 0 && !markdownCharacterEscaped(value, bracket)) {
        var labelEnd = markdownLabelEnd(value, bracket);
        var label = labelEnd >= 0 ? value.slice(bracket + 1, labelEnd) : "";
        if (labelEnd >= 0 && value.charAt(labelEnd + 1) === "(") {
          var destination = markdownDestinationRange(value, labelEnd + 2);
          var linkEnd = markdownInlineLinkEnd(value, labelEnd + 1);
          if (destination && linkEnd >= 0) {
            var target = value.slice(destination.start, destination.end);
            if (targetTest(target)) {
              output += label;
              position = linkEnd + 1;
              continue;
            }
          }
        } else if (labelEnd >= 0 && value.charAt(labelEnd + 1) === "[") {
          var referenceEnd = markdownLabelEnd(value, labelEnd + 1);
          if (referenceEnd >= 0) {
            var reference = value.slice(labelEnd + 2, referenceEnd) || label;
            if (referenceAliases.has(markdownReferenceKey(reference))) {
              output += label;
              position = referenceEnd + 1;
              continue;
            }
          }
        } else if (
          labelEnd >= 0 &&
          referenceAliases.has(markdownReferenceKey(label))
        ) {
          output += label;
          position = labelEnd + 1;
          continue;
        }
      }
      output += value.charAt(position);
      position += 1;
    }
    return output;
  }

  function legacyInternalMarkdownReferences(lines, codeLines, targetTest) {
    targetTest = targetTest || legacyInternalMarkdownTarget;
    var aliases = new Set();
    var definitionLines = new Set();
    var seen = new Set();
    lines.forEach(function (line, lineNumber) {
      if (codeLines.has(lineNumber)) return;
      var definition = markdownReferenceDefinition(line);
      if (!definition || definition.label.charAt(0) === "^") return;
      var key = markdownReferenceKey(definition.label);
      if (seen.has(key)) return;
      seen.add(key);
      if (!targetTest(definition.target)) return;
      aliases.add(key);
      definitionLines.add(lineNumber);
    });
    return {aliases: aliases, definitionLines: definitionLines};
  }

  function legacyBibliographyTarget(target) {
    return /^#bib[.]bib[1-9][0-9]*$/.test(String(target || ""));
  }

  function legacyInternalMarkdownTarget(target) {
    return legacyBibliographyTarget(target) || legacyStructuralTarget(target);
  }

  function markdownReferencedResourcePaths(markdown, resourcePaths) {
    var candidates = new Set(Array.from(resourcePaths.values()));
    var referenced = new Set();
    var normalized = normalizeMarkdown(String(markdown || ""));
    var codeLines = markdownCodeLineIndexes(normalized);
    normalized.split("\n").forEach(
      function (line, lineNumber) {
        if (codeLines.has(lineNumber)) return;
        var definition = markdownReferenceDefinition(line);
        if (definition && candidates.has(definition.target)) {
          referenced.add(definition.target);
        }
        collectMarkdownInlineResourcePaths(line, candidates, referenced);
        collectHtmlResourcePaths(line, candidates, referenced);
      }
    );
    return referenced;
  }

  function collectMarkdownInlineResourcePaths(line, candidates, referenced) {
    var position = 0;
    while (position < line.length) {
      if (line.charAt(position) === "`") {
        var run = 1;
        while (line.charAt(position + run) === "`") run += 1;
        var codeEnd = markdownCodeSpanEnd(line, position + run, run);
        if (codeEnd < 0) return;
        position = codeEnd + run;
        continue;
      }
      var bracket = line.charAt(position) === "[" ? position :
        line.slice(position, position + 2) === "![" ? position + 1 : -1;
      if (bracket >= 0 && !markdownCharacterEscaped(line, bracket)) {
        var labelEnd = markdownLabelEnd(line, bracket);
        if (labelEnd >= 0 && line.charAt(labelEnd + 1) === "(") {
          var destination = markdownDestinationRange(line, labelEnd + 2);
          if (destination) {
            var target = line.slice(destination.start, destination.end);
            if (candidates.has(target)) referenced.add(target);
          }
        }
      }
      position += 1;
    }
  }

  function collectHtmlResourcePaths(line, candidates, referenced) {
    mapMarkdownOutsideCodeSpans(line, function (segment) {
      return transformMarkdownHtmlTags(segment, function (tag) {
        markdownHtmlResourceTargets(tag).forEach(function (target) {
          if (candidates.has(target)) referenced.add(target);
        });
        return tag;
      });
    });
  }

  function stripPortableMarkdownResources(markdown, resourcePaths) {
    var bundledPaths = new Set(Array.from(resourcePaths.values()));
    var normalized = normalizeMarkdown(String(markdown || ""));
    var lines = normalized.split("\n");
    var codeLines = markdownCodeLineIndexes(normalized);
    var localReferences = new Set();
    lines.forEach(function (line, lineNumber) {
      if (codeLines.has(lineNumber)) return;
      var definition = markdownReferenceDefinition(line);
      if (
        definition && definition.label.charAt(0) !== "^" &&
        bundledPaths.has(definition.target)
      ) {
        localReferences.add(markdownReferenceKey(definition.label));
      }
    });
    return lines.map(function (line, lineNumber) {
      if (codeLines.has(lineNumber)) return line;
      var definition = markdownReferenceDefinition(line);
      if (
        definition && definition.label.charAt(0) !== "^" &&
        bundledPaths.has(definition.target)
      ) {
        return "";
      }
      return mapMarkdownOutsideCodeSpans(
        stripMarkdownInlineResources(line, bundledPaths, localReferences),
        stripMarkdownHtmlImages
      );
    }).join("\n");
  }

  function markdownReferenceDefinition(line) {
    var match = /^((?: {0,3}> ?)*(?: {0,3})\[([^\]\n]+)\]:[ \t]*)(<([^>\n]+)>|([^ \t\n]+))(.*)$/.exec(
      line
    );
    if (!match) return null;
    return {
      head: match[1],
      label: match[2],
      target: match[4] === undefined ? match[5] : match[4],
      angled: match[4] !== undefined,
      trailing: match[6]
    };
  }

  function markdownReferenceKey(value) {
    return String(value).trim().replace(/\s+/g, " ").toLowerCase();
  }

  function stripMarkdownInlineResources(line, bundledPaths, localReferences) {
    var output = "";
    var position = 0;
    while (position < line.length) {
      if (line.charAt(position) === "`") {
        var run = 1;
        while (line.charAt(position + run) === "`") run += 1;
        var codeEnd = markdownCodeSpanEnd(line, position + run, run);
        if (codeEnd < 0) return output + line.slice(position);
        output += line.slice(position, codeEnd + run);
        position = codeEnd + run;
        continue;
      }
      var isImage = line.slice(position, position + 2) === "![";
      var bracket = line.charAt(position) === "[" ? position :
        isImage ? position + 1 : -1;
      if (bracket >= 0 && !markdownCharacterEscaped(line, bracket)) {
        var labelEnd = markdownLabelEnd(line, bracket);
        if (labelEnd >= 0) {
          var label = line.slice(bracket + 1, labelEnd);
          if (line.charAt(labelEnd + 1) === "(") {
            var destination = markdownDestinationRange(line, labelEnd + 2);
            var linkEnd = markdownInlineLinkEnd(line, labelEnd + 1);
            if (destination && linkEnd >= 0) {
              var target = line.slice(destination.start, destination.end);
              if (isImage || bundledPaths.has(target)) {
                output += isImage ? markdownFigureText(label) :
                  stripMarkdownResourceLabel(
                    label, bundledPaths, localReferences
                  );
                position = linkEnd + 1;
                continue;
              }
            }
          } else if (line.charAt(labelEnd + 1) === "[") {
            var referenceEnd = markdownLabelEnd(line, labelEnd + 1);
            if (referenceEnd >= 0) {
              var reference = line.slice(labelEnd + 2, referenceEnd) || label;
              if (
                isImage ||
                localReferences.has(markdownReferenceKey(reference))
              ) {
                output += isImage ? markdownFigureText(label) :
                  stripMarkdownResourceLabel(
                    label, bundledPaths, localReferences
                  );
                position = referenceEnd + 1;
                continue;
              }
            }
          } else if (
            isImage || localReferences.has(markdownReferenceKey(label))
          ) {
            output += isImage ? markdownFigureText(label) :
              stripMarkdownResourceLabel(label, bundledPaths, localReferences);
            position = labelEnd + 1;
            continue;
          }
        }
      }
      output += line.charAt(position);
      position += 1;
    }
    return output;
  }

  function stripMarkdownResourceLabel(label, bundledPaths, localReferences) {
    return mapMarkdownOutsideCodeSpans(
      stripMarkdownInlineResources(label, bundledPaths, localReferences),
      stripMarkdownHtmlImages
    );
  }

  function markdownInlineLinkEnd(line, openParenthesis) {
    var depth = 0;
    for (var index = openParenthesis; index < line.length; index += 1) {
      if (markdownCharacterEscaped(line, index)) continue;
      if (line.charAt(index) === "(") {
        depth += 1;
      } else if (line.charAt(index) === ")") {
        depth -= 1;
        if (depth === 0) return index;
      }
    }
    return -1;
  }

  function markdownFigureText(label) {
    var value = String(label || "").trim();
    return value ? "[Figure: " + value + "]" : "";
  }

  function stripMarkdownHtmlImages(line) {
    var value = String(line);
    var output = "";
    var position = 0;
    var imageStart = /<img(?=[\s/>])/ig;
    while (position < value.length) {
      imageStart.lastIndex = position;
      var match = imageStart.exec(value);
      if (!match) return output + value.slice(position);
      output += value.slice(position, match.index);
      var quote = null;
      var end = -1;
      for (var index = imageStart.lastIndex; index < value.length; index += 1) {
        var character = value.charAt(index);
        if (quote) {
          if (character === quote) quote = null;
        } else if (character === '"' || character === "'") {
          quote = character;
        } else if (character === ">") {
          end = index;
          break;
        }
      }
      if (end < 0) return output + value.slice(match.index);
      var tag = value.slice(match.index, end + 1);
      var alt = /\balt\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s>]+))/i.exec(tag);
      output += markdownFigureText(alt ? alt[1] || alt[2] || alt[3] : "");
      position = end + 1;
    }
    return output;
  }

  function rewriteMarkdownReferenceTarget(line, resourcePaths) {
    var definition = markdownReferenceDefinition(line);
    if (!definition || definition.label.charAt(0) === "^") return line;
    var replacement = portableResourceTarget(
      definition.target, resourcePaths
    );
    if (replacement === definition.target) return line;
    return definition.head + (definition.angled ?
      "<" + replacement + ">" : replacement) + definition.trailing;
  }

  function rewriteMarkdownInlineTargets(line, resourcePaths) {
    var output = "";
    var position = 0;
    while (position < line.length) {
      if (line.charAt(position) === "`") {
        var run = 1;
        while (line.charAt(position + run) === "`") run += 1;
        var codeEnd = markdownCodeSpanEnd(line, position + run, run);
        if (codeEnd < 0) return output + line.slice(position);
        output += line.slice(position, codeEnd + run);
        position = codeEnd + run;
        continue;
      }
      var bracket = line.charAt(position) === "[" ? position :
        line.slice(position, position + 2) === "![" ? position + 1 : -1;
      if (bracket >= 0 && !markdownCharacterEscaped(line, bracket)) {
        var labelEnd = markdownLabelEnd(line, bracket);
        if (labelEnd >= 0 && line.charAt(labelEnd + 1) === "(") {
          var destination = markdownDestinationRange(line, labelEnd + 2);
          if (destination) {
            var raw = line.slice(destination.start, destination.end);
            var replacement = portableResourceTarget(raw, resourcePaths);
            if (replacement !== raw) {
              output += line.slice(position, destination.start) + replacement;
              position = destination.end;
              continue;
            }
          }
        }
      }
      output += line.charAt(position);
      position += 1;
    }
    return output;
  }

  function markdownCodeSpanEnd(line, start, delimiterLength) {
    var position = start;
    while (position < line.length) {
      if (line.charAt(position) !== "`") {
        position += 1;
        continue;
      }
      var run = 1;
      while (line.charAt(position + run) === "`") run += 1;
      if (run === delimiterLength) return position;
      position += run;
    }
    return -1;
  }

  function markdownLabelEnd(line, start) {
    var depth = 0;
    for (var index = start; index < line.length; index += 1) {
      if (markdownCharacterEscaped(line, index)) continue;
      if (line.charAt(index) === "[") depth += 1;
      if (line.charAt(index) === "]") {
        depth -= 1;
        if (depth === 0) return index;
      }
    }
    return -1;
  }

  function markdownDestinationRange(line, start) {
    while (
      line.charAt(start) === " " || line.charAt(start) === "\t" ||
      line.charAt(start) === "\n"
    ) {
      start += 1;
    }
    if (line.charAt(start) === "<") {
      for (var angle = start + 1; angle < line.length; angle += 1) {
        if (
          line.charAt(angle) === ">" &&
          !markdownCharacterEscaped(line, angle)
        ) {
          return {start: start + 1, end: angle};
        }
      }
      return null;
    }
    var depth = 0;
    for (var index = start; index < line.length; index += 1) {
      var character = line.charAt(index);
      if (markdownCharacterEscaped(line, index)) continue;
      if (character === "(") {
        depth += 1;
      } else if (character === ")") {
        if (depth === 0) return {start: start, end: index};
        depth -= 1;
      } else if (
        (character === " " || character === "\t" || character === "\n") &&
        depth === 0
      ) {
        return {start: start, end: index};
      }
    }
    return null;
  }

  function markdownCharacterEscaped(value, index) {
    var slashes = 0;
    for (
      var cursor = index - 1;
      cursor >= 0 && value.charAt(cursor) === "\\";
      cursor -= 1
    ) {
      slashes += 1;
    }
    return slashes % 2 === 1;
  }

  function utf8Bytes(value) {
    return new TextEncoder().encode(String(value));
  }

  var zipCrcTable = null;

  function buildStoredZip(files) {
    if (!Array.isArray(files) || files.length > 0xffff) {
      throw new Error("Markdown export has too many ZIP entries");
    }
    var ordered = files.map(function (file) {
      var path = String(file.path || "");
      if (
        !path || path.charAt(0) === "/" || path.indexOf("\\") >= 0 ||
        path.split("/").some(function (part) {
          return !part || part === "." || part === "..";
        })
      ) {
        throw new Error("Markdown export ZIP path is unsafe");
      }
      var bytes = file.bytes instanceof Uint8Array ?
        file.bytes : utf8Bytes(file.bytes);
      if (bytes.length > 0xffffffff) {
        throw new Error("Markdown export ZIP entry is too large");
      }
      var name = utf8Bytes(path);
      if (name.length > 0xffff) {
        throw new Error("Markdown export ZIP filename is too long");
      }
      return {path: path, name: name, bytes: bytes};
    }).sort(function (left, right) {
      return comparePortableText(left.path, right.path);
    });
    var localParts = [];
    var centralParts = [];
    var offset = 0;
    ordered.forEach(function (file) {
      var checksum = zipCrc32(file.bytes);
      var local = new Uint8Array(30 + file.name.length);
      var localView = new DataView(local.buffer);
      localView.setUint32(0, 0x04034b50, true);
      localView.setUint16(4, 20, true);
      localView.setUint16(6, 0x0800, true);
      localView.setUint16(8, 0, true);
      localView.setUint16(10, 0, true);
      localView.setUint16(12, 0x0021, true);
      localView.setUint32(14, checksum, true);
      localView.setUint32(18, file.bytes.length, true);
      localView.setUint32(22, file.bytes.length, true);
      localView.setUint16(26, file.name.length, true);
      local.set(file.name, 30);

      var central = new Uint8Array(46 + file.name.length);
      var centralView = new DataView(central.buffer);
      centralView.setUint32(0, 0x02014b50, true);
      centralView.setUint16(4, 20, true);
      centralView.setUint16(6, 20, true);
      centralView.setUint16(8, 0x0800, true);
      centralView.setUint16(10, 0, true);
      centralView.setUint16(12, 0, true);
      centralView.setUint16(14, 0x0021, true);
      centralView.setUint32(16, checksum, true);
      centralView.setUint32(20, file.bytes.length, true);
      centralView.setUint32(24, file.bytes.length, true);
      centralView.setUint16(28, file.name.length, true);
      centralView.setUint32(42, offset, true);
      central.set(file.name, 46);

      localParts.push(local, file.bytes);
      centralParts.push(central);
      offset += local.length + file.bytes.length;
      if (offset > 0xffffffff) {
        throw new Error("Markdown export ZIP is too large");
      }
    });
    var centralOffset = offset;
    var centralSize = centralParts.reduce(function (total, part) {
      return total + part.length;
    }, 0);
    if (centralOffset + centralSize > 0xffffffff) {
      throw new Error("Markdown export ZIP is too large");
    }
    var end = new Uint8Array(22);
    var endView = new DataView(end.buffer);
    endView.setUint32(0, 0x06054b50, true);
    endView.setUint16(8, ordered.length, true);
    endView.setUint16(10, ordered.length, true);
    endView.setUint32(12, centralSize, true);
    endView.setUint32(16, centralOffset, true);
    return new Blob(localParts.concat(centralParts, [end]), {
      type: "application/zip"
    });
  }

  function zipCrc32(bytes) {
    if (!zipCrcTable) {
      zipCrcTable = new Uint32Array(256);
      for (var value = 0; value < 256; value += 1) {
        var current = value;
        for (var bit = 0; bit < 8; bit += 1) {
          current = current & 1 ?
            0xedb88320 ^ (current >>> 1) : current >>> 1;
        }
        zipCrcTable[value] = current >>> 0;
      }
    }
    var crc = 0xffffffff;
    for (var index = 0; index < bytes.length; index += 1) {
      crc = zipCrcTable[(crc ^ bytes[index]) & 0xff] ^ (crc >>> 8);
    }
    return (crc ^ 0xffffffff) >>> 0;
  }

  function markdownHeading(value) {
    return String(value || "")
      .replace(/<\/?[A-Za-z][^>]*>/g, "")
      .replace(/[\r\n]+/g, " ")
      .trim() || "Untitled";
  }

  function readerTitle() {
    var publication = state.payload.publication;
    var profile = publication.reader_profile || {};
    return profile.title || state.payload.reader_title ||
      publication.labels.document_title ||
      sourceTitle(publication.source_document) ||
      publication.labels.untitled_document || "Untitled document";
  }

  function exportFilename(suffix, extension) {
    var title = String(readerTitle()).normalize("NFC")
      .replace(/[\\/:*?"<>|\u0000-\u001f]/g, " ")
      .trim()
      .replace(/[. ]+$/g, "")
      .replace(/\s+/g, "-")
      .slice(0, 80) || "alc-render";
    var role = String(suffix || "export").replace(/[^A-Za-z0-9_-]+/g, "-");
    return title + "-" + role + "." + extension;
  }

  function downloadText(filename, value, mediaType) {
    downloadBlob(filename, new Blob([value], {type: mediaType}));
  }

  function downloadBlob(filename, blob) {
    var url = URL.createObjectURL(blob);
    var link = document.createElement("a");
    link.href = url;
    link.download = filename;
    link.hidden = true;
    document.body.appendChild(link);
    link.click();
    setTimeout(function () {
      link.remove();
      URL.revokeObjectURL(url);
    }, 0);
  }

  function exportRevisionState() {
    var records = [];
    var fragmentOrder = [];
    state.revisions.forEach(function (values, fragmentId) {
      if (
        !state.activeFragmentIds.has(fragmentId) &&
        !browserCreatedHistory(values)
      ) {
        return;
      }
      fragmentOrder.push(fragmentId);
      values.slice().sort(function (left, right) {
        return left.revision - right.revision ||
          left.semantic_digest.localeCompare(right.semantic_digest);
      }).forEach(function (revision) {
        records.push({
          metadata: metadataOnly(revision),
          markdown_body: normalizeMarkdown(revision.markdown_body),
          semantic_digest: revision.semantic_digest
        });
      });
    });
    var positions = new Map(fragmentOrder.map(function (fragmentId, index) {
      return [fragmentId, index];
    }));
    var selected = Array.from(state.selected.values()).filter(function (revision) {
      return positions.has(revision.fragment_id);
    });
    selected.sort(function (left, right) {
      return left.priority - right.priority ||
        positions.get(left.fragment_id) - positions.get(right.fragment_id);
    });
    return {
      revisions: records,
      selected_revision_digests: selected.map(function (revision) {
        return revision.semantic_digest;
      })
    };
  }

  function buildStandaloneExportHtml() {
    if (typeof document !== "undefined" && document.documentElement) {
      captureExportTemplate();
    } else if (!state.exportHtmlTemplate) {
      captureExportTemplate();
    }
    if (!state.exportStandaloneSupported || !state.exportHtmlTemplate) {
      throw new Error(labels().exportUnavailable);
    }
    var payload = JSON.parse(JSON.stringify(state.payload));
    payload.schema_version = "alc.render.reader_payload.v1";
    delete payload.block_manifest;
    delete payload.reader_chunks;
    delete payload.selected_roles;
    delete payload.selected_heading_fragments;
    payload.resources.forEach(function (resource) {
      delete resource.payload_id;
    });
    if (Array.isArray(state.glossaryBase)) {
      payload.publication.glossary = JSON.parse(
        JSON.stringify(state.glossaryBase)
      );
    }
    var revisionState = exportRevisionState();
    payload.revisions = revisionState.revisions;
    payload.selected_revision_digests = revisionState.selected_revision_digests;
    var glossaryState = glossaryRevisionState();
    payload.glossary_revisions = glossaryState.revisions;
    payload.selected_glossary_revision_digests =
      glossaryState.selected_revision_digests;
    var encoded = JSON.stringify(payload).replace(/<\/script/gi, "<\\/script");
    var pattern = /(<script[^>]*\bid=["']alc-render-payload["'][^>]*>)[\s\S]*?(<\/script>)/i;
    if (!pattern.test(state.exportHtmlTemplate)) {
      throw new Error(labels().exportUnavailable);
    }
    var template = state.exportHtmlTemplate;
    if (!/\bdata-alc-export-snapshot=/.test(template)) {
      template = template.replace(
        /<body\b/i, '<body data-alc-export-snapshot="true"'
      );
    }
    return template.replace(
      /<script[^>]*class=["']alc-render-reader-(?:chunk|resource)["'][^>]*>[\s\S]*?<\/script>/gi,
      ""
    ).replace(pattern, function (_match, open, close) {
      return open + encoded + close;
    });
  }

  function activeInlineDraftCard() {
    if (state.activeGlossaryDraft) {
      return document.querySelector(
        '.alc-glossary-row[data-glossary-entry-id="' +
        cssString(state.activeGlossaryDraft.entryId) +
        '"].is-inline-editing'
      );
    }
    if (!state.activeDraft || !state.activeDraft.base) return null;
    return document.querySelector(
      '.alc-fragment[data-fragment-id="' +
      cssString(state.activeDraft.base.fragment_id) + '"].is-inline-editing'
    );
  }

  function closeUnsavedDialog(restoreFocus) {
    var dialog = document.getElementById("alc-unsaved-dialog");
    if (dialog && dialog.open) dialog.close();
    document.getElementById("alc-unsaved-error").hidden = true;
    if (restoreFocus) focusActiveDraft();
  }

  function openUnsavedDialog(quietFocus) {
    var dialog = document.getElementById("alc-unsaved-dialog");
    if (!dialog || dialog.open) return;
    document.getElementById("alc-unsaved-error").hidden = true;
    dialog.showModal();
    var save = document.getElementById("alc-unsaved-save");
    save.removeAttribute("data-initial-focus");
    if (quietFocus) {
      save.setAttribute("data-initial-focus", "true");
      save.addEventListener("blur", function () {
        save.removeAttribute("data-initial-focus");
      }, {once: true});
    }
    save.focus();
  }

  function attemptInlineDraftExit(event) {
    var card = activeInlineDraftCard();
    var advanced = document.getElementById("alc-editor-dialog");
    var guard = document.getElementById("alc-unsaved-dialog");
    if (!card || (advanced && advanced.open) || (guard && guard.open)) return;
    if (card.contains(event.target)) return;
    if (!activeDraftHasChanges()) {
      cancelActiveDraft();
      return;
    }
    event.preventDefault();
    event.stopImmediatePropagation();
    openUnsavedDialog(event.type === "pointerdown");
  }

  function guardUnsavedDraftBeforeUnload(event) {
    if (!activeDraftHasChanges()) return;
    event.preventDefault();
    event.returnValue = "";
  }

  function setupUnsavedDraftDialog() {
    var strings = labels();
    document.getElementById("alc-unsaved-heading").textContent =
      strings.saveCurrentChanges;
    document.getElementById("alc-unsaved-description").textContent =
      strings.saveBeforeExit;
    var close = document.getElementById("alc-unsaved-close");
    close.setAttribute("aria-label", strings.continueEditing);
    document.getElementById("alc-unsaved-discard").textContent =
      strings.discardChanges;
    document.getElementById("alc-unsaved-save").textContent = strings.saveChanges;
    close.addEventListener("click", function () {
      closeUnsavedDialog(true);
    });
    document.getElementById("alc-unsaved-discard").addEventListener(
      "click", function () {
        closeUnsavedDialog(false);
        cancelActiveDraft();
      }
    );
    document.getElementById("alc-unsaved-save").addEventListener(
      "click", async function (event) {
        var save = event.currentTarget;
        var discard = document.getElementById("alc-unsaved-discard");
        var error = document.getElementById("alc-unsaved-error");
        save.disabled = true;
        discard.disabled = true;
        error.hidden = true;
        await saveEditor(event);
        save.disabled = false;
        discard.disabled = false;
        if (!state.activeDraft && !state.activeGlossaryDraft) {
          closeUnsavedDialog(false);
          return;
        }
        error.textContent = strings.saveFailedInEditor;
        error.hidden = false;
      }
    );
    document.addEventListener("pointerdown", attemptInlineDraftExit, true);
    document.addEventListener("click", attemptInlineDraftExit, true);
    window.addEventListener("beforeunload", guardUnsavedDraftBeforeUnload);
  }

  async function setupEditor() {
    var strings = labels();
    setupUnsavedDraftDialog();
    var connect = document.getElementById("alc-connect");
    updateDirectoryControl();
    if (!window.showDirectoryPicker) {
      connect.disabled = true;
      setStatus(strings.noDirectoryApi, "error");
    } else {
      connect.disabled = true;
      await restoreDirectoryHandle();
      updateDirectoryControl();
      connect.disabled = false;
      connect.addEventListener("click", connectDirectory);
    }
    var dialog = document.getElementById("alc-editor-dialog");
    document.getElementById("alc-editor-title-label").textContent =
      strings.title;
    document.getElementById("alc-editor-glossary-source-label").textContent =
      strings.glossarySourceReadOnly;
    document.getElementById("alc-editor-markdown-label").textContent =
      strings.markdown;
    document.getElementById("alc-editor-preview-label").textContent =
      strings.preview;
    document.getElementById("alc-editor-role-label").textContent =
      strings.role;
    document.getElementById("alc-editor-priority-label").textContent =
      strings.priority;
    document.getElementById("alc-editor-colors-label").textContent =
      strings.colors;
    document.getElementById("alc-editor-foreground-label").textContent =
      strings.foreground;
    document.getElementById("alc-editor-background-label").textContent =
      strings.background;
    document.getElementById("alc-editor-colors-reset").textContent =
      strings.roleDefaultColors;
    var deleteButton = document.getElementById("alc-editor-delete");
    deleteButton.textContent = strings.deleteElement;
    deleteButton.setAttribute("aria-label", strings.deleteElementLabel);
    document.getElementById("alc-editor-save").textContent = strings.save;
    document.getElementById("alc-editor-cancel").textContent = strings.cancel;
    var close = document.getElementById("alc-editor-close");
    close.setAttribute("aria-label", strings.close);
    close.title = strings.close;
    var role = document.getElementById("alc-editor-role");
    Array.prototype.forEach.call(
      role.options,
      function (option) { option.textContent = strings[option.value] || option.value; }
    );
    installCustomSelect(role);
    close.onclick = closeEditorDialog;
    document.getElementById("alc-editor-cancel").onclick = closeEditorDialog;
    dialog.addEventListener("cancel", function (event) {
      event.preventDefault();
      if (!state.saveInProgress) closeEditorDialog();
    });
    document.getElementById("alc-editor-title").addEventListener(
      "input", function () {
        syncDraftAndSaveState();
        if (state.activeGlossaryDraft) clearGlossaryValidationError();
      }
    );
    role.addEventListener("change", function () {
      syncDraftAndSaveState();
      rebindDraftAppearanceToGroup();
      markEditorPreviewDirty();
    });
    document.getElementById("alc-editor-priority").addEventListener("input", function () {
      syncDraftAndSaveState();
      rebindDraftAppearanceToGroup();
      markEditorPreviewDirty();
    });
    document.getElementById("alc-editor-markdown").addEventListener("input", function () {
      syncDraftAndSaveState();
      markEditorPreviewDirty();
    });
    renderColorPresets();
    ["foreground", "background"].forEach(function (kind) {
      document.getElementById("alc-editor-" + kind + "-picker").addEventListener(
        "input", function (event) { updateAppearanceFromPicker(kind, event.target); }
      );
      document.getElementById("alc-editor-" + kind).addEventListener(
        "input", function (event) { updateAppearanceFromText(kind, event.target); }
      );
    });
    document.getElementById("alc-editor-colors-reset").addEventListener(
      "click", resetDraftAppearance
    );
    document.getElementById("alc-editor-delete").addEventListener(
      "click", deleteEditor
    );
    document.getElementById("alc-editor-save").addEventListener("click", saveEditor);
  }

  function renderColorPresets() {
    var root = document.getElementById("alc-editor-color-presets");
    root.replaceChildren();
    COLOR_PRESETS.forEach(function (preset) {
      var button = element("button", "alc-color-preset");
      button.type = "button";
      button.title = preset.foreground + " / " + preset.background;
      var swatch = element("span", "alc-color-preset-swatch", "Aa");
      swatch.style.setProperty("--alc-preset-fg", preset.foreground);
      swatch.style.setProperty("--alc-preset-bg", preset.background);
      button.appendChild(swatch);
      button.appendChild(element("span", "", preset.name));
      button.addEventListener("click", function () {
        setDraftAppearance({
          foreground: preset.foreground,
          background: preset.background
        });
      });
      root.appendChild(button);
    });
  }

  function appearanceInputs(kind) {
    return {
      picker: document.getElementById("alc-editor-" + kind + "-picker"),
      text: document.getElementById("alc-editor-" + kind)
    };
  }

  function syncAppearanceControlsFromDraft() {
    if (!state.activeDraft) return;
    var colors = effectiveAppearance(
      state.activeDraft.role, state.activeDraft.appearance
    );
    ["foreground", "background"].forEach(function (kind) {
      var controls = appearanceInputs(kind);
      controls.picker.value = colors[kind];
      controls.text.value = colors[kind];
      controls.text.setCustomValidity("");
      controls.text.removeAttribute("aria-invalid");
    });
  }

  function rebindDraftAppearanceToGroup() {
    if (!state.activeDraft) return;
    var priority = Number(state.activeDraft.priority);
    if (!Number.isInteger(priority) || priority < 1) return;
    state.activeDraft.appearance = appearanceForGroup(
      state.activeDraft.role, priority
    );
    syncAppearanceControlsFromDraft();
    updateDraftSaveButtons();
  }

  function setDraftAppearance(appearance) {
    if (!state.activeDraft || state.saveInProgress) return;
    state.activeDraft.appearance = normalizeAppearance(appearance);
    syncAppearanceControlsFromDraft();
    updateDraftSaveButtons();
    markEditorPreviewDirty();
  }

  function resetDraftAppearance(event) {
    if (event && typeof event.preventDefault === "function") event.preventDefault();
    if (!state.activeDraft || state.saveInProgress) return;
    state.activeDraft.appearance = null;
    syncAppearanceControlsFromDraft();
    updateDraftSaveButtons();
    markEditorPreviewDirty();
  }

  function updateAppearanceFromPicker(kind, picker) {
    if (!state.activeDraft) return;
    var controls = appearanceInputs(kind);
    controls.text.value = picker.value.toLowerCase();
    controls.text.setCustomValidity("");
    controls.text.removeAttribute("aria-invalid");
    updateDraftAppearanceColor(kind, picker.value);
  }

  function updateAppearanceFromText(kind, input) {
    var value = String(input.value || "");
    var valid = HEX_COLOR.test(value);
    input.setCustomValidity(valid ? "" : "Use #RRGGBB");
    input.setAttribute("aria-invalid", String(!valid));
    if (valid) {
      var normalized = value.toLowerCase();
      appearanceInputs(kind).picker.value = normalized;
      updateDraftAppearanceColor(kind, normalized);
    } else {
      updateDraftSaveButtons();
    }
  }

  function updateDraftAppearanceColor(kind, value) {
    if (!state.activeDraft) return;
    var current = effectiveAppearance(
      state.activeDraft.role, state.activeDraft.appearance
    );
    state.activeDraft.appearance = {
      foreground: kind === "foreground" ? normalizeHexColor(value) : current.foreground,
      background: kind === "background" ? normalizeHexColor(value) : current.background
    };
    updateDraftSaveButtons();
    markEditorPreviewDirty();
  }

  function appearanceControlsValid() {
    if (state.activeGlossaryDraft) return true;
    var foreground = document.getElementById("alc-editor-foreground");
    var background = document.getElementById("alc-editor-background");
    if (!foreground || !background) return true;
    return HEX_COLOR.test(foreground.value) && HEX_COLOR.test(background.value);
  }

  function updateDirectoryControl() {
    var connect = document.getElementById("alc-connect");
    if (!connect) return;
    var strings = labels();
    labelToolButton(
      connect,
      state.directory ? strings.changeSaveLocation : strings.newSaveLocation
    );
  }

  async function connectDirectory() {
    if ((state.activeDraft || state.activeGlossaryDraft) && !state.saveInProgress) {
      setStatus(labels().draftActive, "error");
      return false;
    }
    if (
      state.exportInProgress ||
      state.directorySelectionInProgress
    ) {
      setStatus(labels().revisionBusy, "error");
      return false;
    }
    state.directorySelectionInProgress = true;
    var previousDirectory = state.directory;
    try {
      var handle = await window.showDirectoryPicker({
        id: "alc-render-project",
        mode: "readwrite"
      });
      var permission = await handle.requestPermission({mode: "readwrite"});
      if (permission !== "granted") throw new Error("read/write permission was not granted");
      setStatus(labels().loading);
      if (!await loadDirectoryRevisions(handle)) return false;
      await rememberDirectoryHandle(handle);
      updateDirectoryControl();
      setStatus(labels().connected);
      return true;
    } catch (error) {
      if (error && error.name === "AbortError") return false;
      state.directory = previousDirectory;
      updateDirectoryControl();
      setStatus(String(error.message || error), "error");
      return false;
    } finally {
      state.directorySelectionInProgress = false;
    }
  }

  async function loadDirectoryRevisions(directory) {
    var handle = directory || state.directory;
    if (!handle) return false;
    loadAllPayload(false);
    var generation = state.directoryLoadGeneration + 1;
    state.directoryLoadGeneration = generation;
    var revisions = new Map();
    var revisionDigests = new Map();
    var fileDiagnostics = [];
    state.embeddedRevisions.forEach(function (revision) {
      addRevisionTo(revision, revisions, fileDiagnostics, revisionDigests);
    });
    var previousCache = handle === state.directoryCacheHandle ?
      state.directoryFileCache : new Map();
    var nextCache = new Map();
    var fragments;
    try {
      fragments = await handle.getDirectoryHandle("fragments");
    } catch (error) {
      if (error.name === "NotFoundError") {
        var missingFragmentsGlossary = await loadDirectoryGlossaryRevisions(
          handle, revisions
        );
        return commitDirectorySnapshot(
          handle, revisions, revisionDigests, fileDiagnostics, nextCache,
          generation, missingFragmentsGlossary
        );
      }
      throw error;
    }
    var files = await collectMarkdownFiles(fragments);
    var outcomes = await loadDirectoryRevisionFiles(
      files, embeddedRevisionFilenames(), previousCache, nextCache
    );
    outcomes.forEach(function (outcome) {
      if (!outcome) return;
      if (outcome.revision) {
        addRevisionTo(
          outcome.revision, revisions, fileDiagnostics, revisionDigests
        );
      } else if (outcome.diagnostic) {
        fileDiagnostics.push(outcome.diagnostic);
      }
    });
    var glossarySnapshot = await loadDirectoryGlossaryRevisions(
      handle, revisions
    );
    return commitDirectorySnapshot(
      handle, revisions, revisionDigests, fileDiagnostics, nextCache,
      generation, glossarySnapshot
    );
  }

  function commitDirectorySnapshot(
    handle, revisions, revisionDigests, fileDiagnostics, fileCache, generation,
    glossarySnapshot
  ) {
    if (generation !== state.directoryLoadGeneration) return false;
    var previousSelected = new Map(state.selected);
    var previousGlossary = new Map(state.selectedGlossary);
    if (glossarySnapshot) {
      state.glossaryRevisions = glossarySnapshot.revisions;
      state.glossaryRevisionDigests = glossarySnapshot.revisionDigests;
      state.glossaryFileDiagnostics = glossarySnapshot.diagnostics;
      state.glossaryDirectoryCacheHandle = handle;
      state.glossaryFileCache = glossarySnapshot.fileCache;
      resolveGlossaryAll();
      glossarySnapshot.batchRevisions.forEach(function (revision) {
        addRevisionTo(revision, revisions, fileDiagnostics, revisionDigests);
      });
    }
    state.directory = handle;
    state.revisions = revisions;
    state.revisionDigests = revisionDigests;
    state.fileDiagnostics = fileDiagnostics;
    state.directoryCacheHandle = handle;
    state.directoryFileCache = fileCache;
    resolveAll();
    refreshChangedSelections(previousSelected);
    if (glossarySnapshot) {
      state.payload.glossary_revisions = glossaryRevisionState().revisions;
      refreshGlossarySurfaces(previousGlossary);
    }
    return true;
  }

  function embeddedRevisionFilenames() {
    var filenames = new Set();
    state.embeddedRevisions.forEach(function (raw) {
      var metadata = raw.metadata || raw;
      var digest = raw.semantic_digest || metadata.semantic_digest;
      if (
        positiveInteger(metadata.revision) &&
        typeof digest === "string" &&
        /^[0-9a-f]{64}$/.test(digest)
      ) {
        filenames.add(revisionFilename(metadata.revision, digest));
      }
    });
    return filenames;
  }

  async function loadDirectoryRevisionFiles(
    files, embeddedFilenames, previousCache, nextCache
  ) {
    var outcomes = new Array(files.length);
    var nextIndex = 0;
    async function worker() {
      while (true) {
        var index = nextIndex;
        nextIndex += 1;
        if (index >= files.length) return;
        outcomes[index] = await loadDirectoryRevisionFile(
          files[index], embeddedFilenames, previousCache, nextCache
        );
      }
    }
    var workers = [];
    var workerCount = Math.min(DIRECTORY_READ_CONCURRENCY, files.length);
    for (var index = 0; index < workerCount; index += 1) {
      workers.push(worker());
    }
    await Promise.all(workers);
    return outcomes;
  }

  async function loadDirectoryRevisionFile(
    entry, embeddedFilenames, previousCache, nextCache
  ) {
    if (embeddedFilenames.has(entry.name)) return null;
    var key = JSON.stringify(entry.path);
    var file;
    try {
      file = await entry.handle.getFile();
    } catch (error) {
      return {
        diagnostic: "Ignored invalid fragment file " + entry.name + ": " +
          String(error.message || error)
      };
    }
    var stamp = String(file.size) + ":" + String(file.lastModified);
    var cached = previousCache.get(key);
    if (cached && cached.stamp === stamp) {
      nextCache.set(key, cached);
      return cached.outcome;
    }
    var outcome;
    try {
      var revision = await parseRevisionFile(await file.text(), entry.name);
      revision._origin = "directory";
      outcome = {revision: revision};
    } catch (error) {
      outcome = {
        diagnostic: "Ignored invalid fragment file " + entry.name + ": " +
          String(error.message || error)
      };
    }
    nextCache.set(key, {stamp: stamp, outcome: outcome});
    return outcome;
  }

  async function loadDirectoryGlossaryRevisions(directory, fragmentRevisions) {
    var candidates = [];
    var diagnostics = [];
    state.embeddedGlossaryRevisions.forEach(function (revision) {
      candidates.push(revision);
    });
    var previousCache = directory === state.glossaryDirectoryCacheHandle ?
      state.glossaryFileCache : new Map();
    var nextCache = new Map();
    var glossary;
    try {
      glossary = await directory.getDirectoryHandle("glossary");
    } catch (error) {
      if (error.name === "NotFoundError") {
        var embedded = buildCommittedGlossarySnapshot(
          candidates, new Map(), fragmentRevisions, diagnostics
        );
        embedded.fileCache = nextCache;
        return embedded;
      }
      throw error;
    }
    var files = await collectGlossaryFiles(glossary);
    var outcomes = await loadDirectoryGlossaryRevisionFiles(
      files, previousCache, nextCache
    );
    var batchRevisionsByGlossaryDigest = new Map();
    for (var outcomeIndex = 0; outcomeIndex < outcomes.length; outcomeIndex += 1) {
      var outcome = outcomes[outcomeIndex];
      if (!outcome) continue;
      if (outcome.revision) {
        try {
          var batch = await loadGlossaryPropagationBatch(
            directory, outcome.revision
          );
          candidates.push(outcome.revision);
          batch.glossaryRevisions.forEach(function (revision) {
            candidates.push(revision);
          });
          if (batch.fragments.length || batch.glossaryRevisions.length) {
            batchRevisionsByGlossaryDigest.set(
              outcome.revision.semantic_digest, batch
            );
          }
        } catch (error) {
          diagnostics.push(
            "Ignored incomplete glossary propagation " +
            outcome.revision.entry_id + " v" + outcome.revision.revision + ": " +
            String(error.message || error)
          );
        }
      } else if (outcome.diagnostic) {
        diagnostics.push(outcome.diagnostic);
      }
    }
    var snapshot = buildCommittedGlossarySnapshot(
      candidates, batchRevisionsByGlossaryDigest, fragmentRevisions, diagnostics
    );
    snapshot.fileCache = nextCache;
    return snapshot;
  }

  async function fileHandleAtRelativePath(directory, path) {
    var segments = String(path || "").split("/");
    var handle = directory;
    for (var index = 0; index < segments.length - 1; index += 1) {
      if (!portableIdentifier(segments[index])) {
        throw new Error("propagation path is invalid");
      }
      handle = await handle.getDirectoryHandle(segments[index]);
    }
    return handle.getFileHandle(segments[segments.length - 1]);
  }

  async function loadGlossaryPropagationBatch(directory, glossaryRevision) {
    var propagation = glossaryRevision.provenance &&
      glossaryRevision.provenance.propagation;
    if (propagation === undefined) {
      return {fragments: [], glossaryRevisions: []};
    }
    validateGlossaryPropagation(propagation);
    var revisions = [];
    for (var index = 0; index < propagation.fragments.length; index += 1) {
      var reference = propagation.fragments[index];
      var handle = await fileHandleAtRelativePath(directory, reference.path);
      var revision = await parseRevisionFile(
        await (await handle.getFile()).text(),
        reference.path.split("/").pop()
      );
      if (revision.fragment_id !== reference.fragment_id ||
        revision.revision !== reference.revision ||
        revision.parent_semantic_digest !== reference.parent_semantic_digest ||
        revision.semantic_digest !== reference.semantic_digest ||
        !revision.provenance ||
        revision.provenance.reason !== "glossary-propagation" ||
        revision.provenance.propagation_batch_id !== propagation.batch_id ||
        revision.provenance.glossary_entry_id !== glossaryRevision.entry_id) {
        throw new Error("propagation fragment does not match its commit marker");
      }
      validateStoredGlossaryMentions(
        revision, revision.markdown_body, state.glossaryBase
      );
      revision._origin = "directory";
      revisions.push(revision);
    }
    var glossaryRevisions = [];
    var dependentReferences = propagation.glossary_revisions || [];
    for (var dependentIndex = 0;
      dependentIndex < dependentReferences.length; dependentIndex += 1) {
      var dependentReference = dependentReferences[dependentIndex];
      var dependentHandle = await fileHandleAtRelativePath(
        directory, dependentReference.path
      );
      var dependent = await parseGlossaryRevisionFile(
        await (await dependentHandle.getFile()).text(),
        dependentReference.path.split("/").pop()
      );
      var base = glossaryBaseEntry(dependentReference.entry_id);
      if (!base || state.glossaryDuplicateIds.has(dependent.entry_id) ||
        dependent.entry_id === glossaryRevision.entry_id ||
        dependent.entry_id !== dependentReference.entry_id ||
        dependent.revision !== dependentReference.revision ||
        dependent.parent_semantic_digest !==
          dependentReference.parent_semantic_digest ||
        dependent.semantic_digest !== dependentReference.semantic_digest ||
        !dependent.provenance ||
        dependent.provenance.reason !== "glossary-propagation" ||
        dependent.provenance.propagation_batch_id !== propagation.batch_id ||
        dependent.provenance.glossary_entry_id !== glossaryRevision.entry_id ||
        dependent.provenance.propagation !== undefined ||
        !validGlossaryRevisionChange(base, dependent.entry)) {
        throw new Error(
          "dependent glossary revision does not match its commit marker"
        );
      }
      dependent._origin = "directory";
      glossaryRevisions.push(dependent);
    }
    return {fragments: revisions, glossaryRevisions: glossaryRevisions};
  }

  function structurallySelectedGlossaryChains(revisions) {
    var chains = [];
    state.glossaryBase.forEach(function (base) {
      var entryId = glossaryEntryId(base);
      var baseDigest = state.glossaryBaseDigests.get(entryId);
      if (!entryId || !baseDigest) return;
      var values = (revisions.get(entryId) || []).filter(function (revision) {
        return validGlossaryRevisionChange(base, revision.entry);
      });
      var byDigest = new Map(values.map(function (revision) {
        return [revision.semantic_digest, revision];
      }));
      var children = new Map();
      values.forEach(function (revision) {
        var parentRevision = byDigest.get(revision.parent_semantic_digest);
        var expected = revision.parent_semantic_digest === baseDigest ? 2 :
          parentRevision ? parentRevision.revision + 1 : null;
        if (revision.revision !== expected) return;
        var list = children.get(revision.parent_semantic_digest) || [];
        list.push(revision);
        children.set(revision.parent_semantic_digest, list);
      });
      var parent = baseDigest;
      var chain = [];
      while ((children.get(parent) || []).length) {
        var candidates = children.get(parent);
        var next = candidates.length === 1 ? candidates[0] :
          equivalentGlossaryChild(candidates, children);
        if (!next) break;
        chain.push(next);
        parent = next.semantic_digest;
      }
      chains.push(chain);
    });
    return chains;
  }

  function glossaryRevisionDescendsFrom(revision, rejected, byDigest) {
    var current = revision;
    while (current) {
      if (rejected.has(current.semantic_digest)) return true;
      current = byDigest.get(current.parent_semantic_digest) || null;
    }
    return false;
  }

  function normalizedGlossaryBatch(value) {
    if (Array.isArray(value)) {
      return {fragments: value, glossaryRevisions: []};
    }
    return {
      fragments: value && Array.isArray(value.fragments) ?
        value.fragments : [],
      glossaryRevisions: value && Array.isArray(value.glossaryRevisions) ?
        value.glossaryRevisions : []
    };
  }

  function buildCommittedGlossarySnapshot(
    candidates, batchRevisionsByGlossaryDigest, fragmentRevisions, diagnostics
  ) {
    var batches = new Map();
    var dependentOwners = new Map();
    batchRevisionsByGlossaryDigest.forEach(function (value, ownerDigest) {
      var batch = normalizedGlossaryBatch(value);
      batches.set(ownerDigest, batch);
      batch.glossaryRevisions.forEach(function (revision) {
        dependentOwners.set(revision.semantic_digest, ownerDigest);
      });
    });
    var remaining = candidates.slice();
    var revisions = new Map();
    var revisionDigests = new Map();
    var accepted = [];
    while (true) {
      revisions = new Map();
      revisionDigests = new Map();
      remaining.forEach(function (revision) {
        addGlossaryRevisionTo(
          revision, revisions, diagnostics, revisionDigests
        );
      });
      var selectedBatches = [];
      var selectedDigests = new Set();
      structurallySelectedGlossaryChains(revisions).forEach(function (chain) {
        chain.forEach(function (revision) {
          selectedDigests.add(revision.semantic_digest);
          var batch = batches.get(revision.semantic_digest);
          if (batch) {
            selectedBatches.push({glossary: revision, members: batch});
          }
        });
      });
      var rejected = new Set();
      selectedBatches.forEach(function (batch) {
        if (batch.members.glossaryRevisions.some(function (revision) {
          return !selectedDigests.has(revision.semantic_digest);
        })) {
          rejected.add(batch.glossary.semantic_digest);
        }
      });
      dependentOwners.forEach(function (ownerDigest, dependentDigest) {
        if (selectedDigests.has(dependentDigest) &&
          !selectedDigests.has(ownerDigest)) {
          rejected.add(dependentDigest);
        }
      });
      accepted = [];
      var acceptedFragments = [];
      var pending = selectedBatches.filter(function (batch) {
        return !rejected.has(batch.glossary.semantic_digest);
      });
      while (pending.length) {
        var heads = glossaryBatchFragmentHeads(
          fragmentRevisions, acceptedFragments
        );
        var ready = pending.filter(function (batch) {
          return batch.members.fragments.every(function (fragment) {
            var head = heads.get(fragment.fragment_id);
            return head && (
              head.semantic_digest === fragment.semantic_digest ||
              (
                head.semantic_digest === fragment.parent_semantic_digest &&
                fragment.revision === head.revision + 1 &&
                stableStringify(fragment.source) === stableStringify(head.source) &&
                stableStringify(fragment.anchor) === stableStringify(head.anchor)
              )
            );
          });
        });
        var conflicted = new Set();
        var owners = new Map();
        ready.forEach(function (batch) {
          batch.members.fragments.forEach(function (fragment) {
            var head = heads.get(fragment.fragment_id);
            if (head && head.semantic_digest === fragment.semantic_digest) return;
            var owner = owners.get(fragment.fragment_id);
            if (owner) {
              conflicted.add(owner);
              conflicted.add(batch);
            } else {
              owners.set(fragment.fragment_id, batch);
            }
          });
        });
        var applicable = ready.filter(function (batch) {
          return !conflicted.has(batch);
        });
        if (!applicable.length) break;
        applicable.forEach(function (batch) {
          accepted.push(batch);
          batch.members.fragments.forEach(function (fragment) {
            acceptedFragments.push(fragment);
          });
        });
        pending = pending.filter(function (batch) {
          return applicable.indexOf(batch) < 0;
        });
      }
      pending.forEach(function (batch) {
        rejected.add(batch.glossary.semantic_digest);
      });
      selectedBatches.forEach(function (batch) {
        if (!rejected.has(batch.glossary.semantic_digest)) return;
        batch.members.glossaryRevisions.forEach(function (revision) {
          rejected.add(revision.semantic_digest);
        });
      });
      if (!rejected.size) break;
      selectedBatches.forEach(function (batch) {
        if (!rejected.has(batch.glossary.semantic_digest)) return;
        diagnostics.push(
          "Ignored glossary propagation with a stale or conflicting member parent: " +
          batch.glossary.entry_id + " v" + batch.glossary.revision
        );
      });
      var nextRemaining = [];
      revisions.forEach(function (values) {
        var byDigest = new Map(values.map(function (revision) {
          return [revision.semantic_digest, revision];
        }));
        values.forEach(function (revision) {
          if (!glossaryRevisionDescendsFrom(revision, rejected, byDigest)) {
            nextRemaining.push(revision);
          }
        });
      });
      remaining = nextRemaining;
    }
    var acceptedDigests = new Set();
    structurallySelectedGlossaryChains(revisions).forEach(function (chain) {
      chain.forEach(function (revision) {
        acceptedDigests.add(revision.semantic_digest);
      });
    });
    var batchRevisions = [];
    accepted.forEach(function (batch) {
      if (acceptedDigests.has(batch.glossary.semantic_digest)) {
        batchRevisions = batchRevisions.concat(batch.members.fragments);
      }
    });
    return {
      revisions: revisions,
      revisionDigests: revisionDigests,
      diagnostics: diagnostics,
      batchRevisions: batchRevisions,
      fileCache: new Map()
    };
  }

  function glossaryBatchFragmentHeads(fragmentRevisions, acceptedFragments) {
    var grouped = new Map();
    fragmentRevisions.forEach(function (values, fragmentId) {
      grouped.set(fragmentId, values.slice());
    });
    acceptedFragments.forEach(function (revision) {
      var values = grouped.get(revision.fragment_id) || [];
      values.push(revision);
      grouped.set(revision.fragment_id, values);
    });
    var heads = new Map();
    grouped.forEach(function (values, fragmentId) {
      var resolved = resolveFragment(values, fragmentId);
      if (resolved.selected && !resolved.conflicted) {
        heads.set(fragmentId, resolved.selected);
      }
    });
    return heads;
  }

  async function loadDirectoryGlossaryRevisionFiles(files, previousCache, nextCache) {
    var outcomes = new Array(files.length);
    var nextIndex = 0;
    async function worker() {
      while (true) {
        var index = nextIndex;
        nextIndex += 1;
        if (index >= files.length) return;
        outcomes[index] = await loadDirectoryGlossaryRevisionFile(
          files[index], previousCache, nextCache
        );
      }
    }
    var workers = [];
    for (var index = 0; index < Math.min(DIRECTORY_READ_CONCURRENCY, files.length); index += 1) {
      workers.push(worker());
    }
    await Promise.all(workers);
    return outcomes;
  }

  async function loadDirectoryGlossaryRevisionFile(entry, previousCache, nextCache) {
    var key = JSON.stringify(entry.path);
    var file;
    try {
      file = await entry.handle.getFile();
    } catch (error) {
      return {diagnostic: "Ignored invalid glossary file " + entry.name + ": " +
        String(error.message || error)};
    }
    var stamp = String(file.size) + ":" + String(file.lastModified);
    var cached = previousCache.get(key);
    if (cached && cached.stamp === stamp) {
      nextCache.set(key, cached);
      return cached.outcome;
    }
    var outcome;
    try {
      var revision = await parseGlossaryRevisionFile(await file.text(), entry.name);
      revision._origin = "directory";
      outcome = {revision: revision};
    } catch (error) {
      outcome = {diagnostic: "Ignored invalid glossary file " + entry.name + ": " +
        String(error.message || error)};
    }
    nextCache.set(key, {stamp: stamp, outcome: outcome});
    return outcome;
  }

  async function collectMarkdownFiles(directory) {
    var output = [];
    var pending = [{handle: directory, path: []}];
    while (pending.length) {
      var batch = pending.splice(0, DIRECTORY_READ_CONCURRENCY);
      var scans = await Promise.all(batch.map(scanMarkdownDirectory));
      scans.forEach(function (scan) {
        output = output.concat(scan.files);
        pending = pending.concat(scan.directories);
      });
    }
    output.sort(function (left, right) {
      return JSON.stringify(left.path).localeCompare(JSON.stringify(right.path));
    });
    return output;
  }

  async function scanMarkdownDirectory(item) {
    var directories = [];
    var files = [];
    for await (var entry of item.handle.values()) {
      var path = item.path.concat([entry.name]);
      if (entry.kind === "directory") {
        directories.push({handle: entry, path: path});
      } else if (entry.kind === "file" && entry.name.endsWith(".md")) {
        files.push({handle: entry, name: entry.name, path: path});
      }
    }
    directories.sort(function (left, right) {
      return JSON.stringify(left.path).localeCompare(JSON.stringify(right.path));
    });
    files.sort(function (left, right) {
      return JSON.stringify(left.path).localeCompare(JSON.stringify(right.path));
    });
    return {directories: directories, files: files};
  }

  async function collectGlossaryFiles(directory) {
    var output = [];
    var pending = [{handle: directory, path: []}];
    while (pending.length) {
      var batch = pending.splice(0, DIRECTORY_READ_CONCURRENCY);
      var scans = await Promise.all(batch.map(scanGlossaryDirectory));
      scans.forEach(function (scan) {
        output = output.concat(scan.files);
        pending = pending.concat(scan.directories);
      });
    }
    output.sort(function (left, right) {
      return JSON.stringify(left.path).localeCompare(JSON.stringify(right.path));
    });
    return output;
  }

  async function scanGlossaryDirectory(item) {
    var directories = [];
    var files = [];
    for await (var entry of item.handle.values()) {
      var path = item.path.concat([entry.name]);
      if (entry.kind === "directory") {
        directories.push({handle: entry, path: path});
      } else if (
        entry.kind === "file" &&
        (entry.name.endsWith(".md") || entry.name.endsWith(".json"))
      ) {
        files.push({handle: entry, name: entry.name, path: path});
      }
    }
    directories.sort(function (left, right) {
      return JSON.stringify(left.path).localeCompare(JSON.stringify(right.path));
    });
    files.sort(function (left, right) {
      return JSON.stringify(left.path).localeCompare(JSON.stringify(right.path));
    });
    return {directories: directories, files: files};
  }

  function openEditEditor(fragment) {
    beginInlineEdit(fragment);
  }

  function beginGlossaryEdit(entry, focusField) {
    if (state.exportInProgress || state.directorySelectionInProgress || state.saveInProgress) {
      setStatus(labels().revisionBusy, "error");
      return;
    }
    if (!glossaryEntryEditableInState(entry)) return;
    if (state.activeGlossaryDraft) {
      if (state.activeGlossaryDraft.entryId === glossaryEntryId(entry)) {
        focusActiveDraft();
        return;
      }
      if (!prepareForDraftSwitch()) return;
    }
    if (!prepareForDraftSwitch()) return;
    var entryId = glossaryEntryId(entry);
    var currentRevision = state.selectedGlossaryRevisions.get(entryId);
    state.activeGlossaryDraft = {
      base: JSON.parse(JSON.stringify(entry)),
      entryId: entryId,
      baseDigest: selectedGlossaryDigest(entryId),
      baseRevision: currentRevision ? currentRevision.revision : 1,
      translated_term: String(entry[glossaryTranslatedKey(entry)] || ""),
      definition: String(entry.definition || "")
    };
    state.editorKind = "glossary";
    state.editorBase = state.activeGlossaryDraft.base;
    state.editorHistorical = null;
    state.editorAnchor = null;
    clearGlossaryValidationError();
    replaceGlossaryRow(entryId);
    focusGlossaryInlineEditor(entryId, focusField);
  }

  function beginInlineEdit(fragment) {
    if (state.exportInProgress || state.directorySelectionInProgress) {
      setStatus(labels().revisionBusy, "error");
      return;
    }
    if (state.saveInProgress) return;
    if (state.activeGlossaryDraft && !prepareForDraftSwitch()) return;
    if (state.activeDraft) {
      if (
        state.activeDraft.base &&
        state.activeDraft.base.fragment_id === fragment.fragment_id
      ) {
        focusActiveDraft();
        return;
      }
      if (!prepareForDraftSwitch()) return;
    }
    state.editorKind = "fragment";
    state.activeDraft = draftFromFragment(fragment);
    state.editorBase = fragment;
    state.editorAnchor = fragment.anchor;
    state.editorHistorical = fragment;
    replaceFragmentCard(fragment.fragment_id, fragment.anchor);
    focusInlineEditor(fragment.fragment_id);
  }

  function draftFromFragment(fragment) {
    return {
      base: fragment,
      anchor: JSON.parse(JSON.stringify(fragment.anchor)),
      title: fragment.title || null,
      role: fragment.role,
      priority: fragment.priority,
      markdown_body: fragment.markdown_body || "",
      appearance: appearanceForGroup(fragment.role, fragment.priority)
    };
  }

  function focusInlineEditor(fragmentId) {
    window.requestAnimationFrame(function () {
      var card = document.querySelector(
        '.alc-fragment[data-fragment-id="' + cssString(fragmentId) + '"]'
      );
      if (card && typeof card.scrollIntoView === "function") {
        card.scrollIntoView({block: "center", behavior: "auto"});
      }
      var textarea = card && card.querySelector(".alc-inline-markdown");
      if (textarea) textarea.focus();
    });
  }

  function focusGlossaryInlineEditor(entryId, focusField) {
    window.requestAnimationFrame(function () {
      var row = document.querySelector(
        '.alc-glossary-row[data-glossary-entry-id="' +
        cssString(entryId) + '"].is-inline-editing'
      );
      if (row && typeof row.scrollIntoView === "function") {
        row.scrollIntoView({block: "center", behavior: "auto"});
      }
      var selector = focusField === "translation" ?
        ".alc-glossary-inline-input" : ".alc-glossary-inline-definition";
      var control = row && row.querySelector(selector);
      if (control && typeof control.focus === "function") {
        control.focus();
      }
    });
  }

  function focusActiveDraft() {
    if (state.activeGlossaryDraft) {
      var glossaryDialog = document.getElementById("alc-editor-dialog");
      if (glossaryDialog && glossaryDialog.open) {
        var glossaryInput = document.getElementById("alc-editor-title");
        if (glossaryInput && typeof glossaryInput.focus === "function") glossaryInput.focus();
      } else {
        focusGlossaryInlineEditor(state.activeGlossaryDraft.entryId);
      }
      return;
    }
    if (!state.activeDraft) return;
    var dialog = document.getElementById("alc-editor-dialog");
    if (dialog && dialog.open) {
      var markdown = document.getElementById("alc-editor-markdown");
      if (markdown && typeof markdown.focus === "function") markdown.focus();
      return;
    }
    if (state.activeDraft.base) {
      focusInlineEditor(state.activeDraft.base.fragment_id);
    }
  }

  function prepareForDraftSwitch() {
    if (!state.activeDraft && !state.activeGlossaryDraft) return true;
    if (activeDraftHasChanges()) {
      setStatus(labels().draftRedirected, "error");
      focusActiveDraft();
      return false;
    }
    cancelActiveDraft();
    return true;
  }

  function cssString(value) {
    if (window.CSS && typeof window.CSS.escape === "function") {
      return window.CSS.escape(String(value));
    }
    return String(value).replace(/["\\]/g, "\\$&");
  }

  function openNewEditor(block) {
    openNewEditorForAnchor({
      kind: "block",
      target_id: block.block_id,
      related_blocks: [anchorBlock(block)]
    });
  }

  function openNewEditorForAnchor(anchor) {
    if (state.exportInProgress || state.directorySelectionInProgress) {
      setStatus(labels().revisionBusy, "error");
      return;
    }
    if (!prepareForDraftSwitch()) return;
    var recoverable = recoverableFragmentAtAnchor(anchor);
    if (recoverable) {
      state.activeDraft = draftFromFragment(recoverable);
      state.activeDraft.title = null;
      state.activeDraft.markdown_body = "";
      state.editorBase = recoverable;
      state.editorHistorical = latestEarlierRevision(recoverable);
      state.editorAnchor = recoverable.anchor;
      openAdvancedEditor(null, labels().newNote);
      return;
    }
    state.activeDraft = {
      base: null,
      anchor: JSON.parse(JSON.stringify(anchor)),
      title: null,
      role: "note",
      priority: 110,
      markdown_body: "",
      appearance: appearanceForGroup("note", 110)
    };
    state.editorBase = null;
    state.editorHistorical = null;
    state.editorAnchor = anchor;
    openAdvancedEditor(null, labels().newNote);
  }

  function recoverableFragmentAtAnchor(anchor) {
    var candidates = Array.from(state.selected.values()).filter(function (fragment) {
      return !fragmentIsVisible(fragment) && fragment.anchor &&
        fragment.anchor.kind === anchor.kind &&
        fragment.anchor.target_id === anchor.target_id;
    });
    candidates.sort(function (left, right) {
      var leftEdited = String((left.provenance || {}).edited_at || "");
      var rightEdited = String((right.provenance || {}).edited_at || "");
      return rightEdited.localeCompare(leftEdited) ||
        right.revision - left.revision ||
        left.fragment_id.localeCompare(right.fragment_id);
    });
    return candidates[0] || null;
  }

  function latestEarlierRevision(fragment) {
    var revisions = state.revisions.get(fragment.fragment_id) || [];
    var parent = revisions.find(function (revision) {
      return revision.semantic_digest === fragment.parent_semantic_digest;
    });
    if (parent) return parent;
    return revisions.filter(function (revision) {
      return revision.semantic_digest !== fragment.semantic_digest;
    }).sort(function (left, right) {
      return right.revision - left.revision ||
        left.semantic_digest.localeCompare(right.semantic_digest);
    })[0] || fragment;
  }

  function openAdvancedEditor(event, heading) {
    if (event && typeof event.preventDefault === "function") event.preventDefault();
    if ((!state.activeDraft && !state.activeGlossaryDraft) || state.saveInProgress) return;
    var dialog = document.getElementById("alc-editor-dialog");
    var draft = state.activeDraft;
    var glossaryMode = state.editorKind === "glossary" &&
      state.activeGlossaryDraft;
    dialog.dataset.editorKind = glossaryMode ? "glossary" : "fragment";
    state.editorGeneration += 1;
    document.getElementById("alc-editor-heading").textContent =
      heading || (glossaryMode ? labels().glossaryEditor : labels().editor);
    var sourceField = null;
    try {
      sourceField = document.getElementById("alc-editor-glossary-source-field");
    } catch (_error) {
      sourceField = null;
    }
    var advanced = null;
    try {
      advanced = document.getElementById("alc-editor-advanced");
    } catch (_error) {
      advanced = null;
    }
    if (glossaryMode) {
      draft = state.activeGlossaryDraft;
      clearGlossaryValidationError();
      setOptionalText("alc-editor-title-label", labels().translatedTerm);
      setOptionalText("alc-editor-markdown-label", labels().definition);
      document.getElementById("alc-editor-glossary-source").value = glossarySourceTerm(draft.base);
      if (sourceField) sourceField.hidden = false;
      if (advanced) advanced.hidden = false;
      setOptionalHidden(".alc-dialog-advanced-fields", true);
      setOptionalHidden(".alc-appearance-editor", true);
    } else {
      setOptionalText("alc-editor-title-label", labels().title);
      setOptionalText("alc-editor-markdown-label", labels().markdown);
      if (sourceField) sourceField.hidden = true;
      if (advanced) advanced.hidden = false;
      setOptionalHidden(".alc-dialog-advanced-fields", false);
      setOptionalHidden(".alc-appearance-editor", false);
    }
    document.getElementById("alc-editor-title").value = draft.title || "";
    if (glossaryMode) {
      document.getElementById("alc-editor-title").value = draft.translated_term;
      document.getElementById("alc-editor-markdown").value = draft.definition;
    } else {
      var role = document.getElementById("alc-editor-role");
      role.value = draft.role || "note";
      syncCustomSelect(role);
      document.getElementById("alc-editor-priority").value = String(draft.priority || 110);
      document.getElementById("alc-editor-markdown").value = draft.markdown_body || "";
      syncAppearanceControlsFromDraft();
    }
    state.editorPreviewDirty = true;
    var deleteButton = document.getElementById("alc-editor-delete");
    if (deleteButton) {
      deleteButton.hidden = glossaryMode || !draft.base || draft.base.deleted === true;
    }
    if (glossaryMode) renderGlossaryHistory(draft.entryId);
    else renderHistory(draft.base && draft.base.fragment_id);
    updatePreview();
    updateDraftSaveButtons();
    dialog.showModal();
  }

  function closeEditorDialog() {
    if (state.saveInProgress) return;
    var dialog = document.getElementById("alc-editor-dialog");
    if (state.activeGlossaryDraft) {
      syncDraftFromDialog();
      var entryId = state.activeGlossaryDraft.entryId;
      if (dialog && dialog.open) dialog.close();
      replaceGlossaryRow(entryId);
      focusGlossaryInlineEditor(entryId);
      return;
    }
    if (!state.activeDraft) {
      if (dialog.open) dialog.close();
      return;
    }
    syncDraftFromDialog();
    if (!state.activeDraft.base) {
      state.activeDraft = null;
      state.editorBase = null;
      state.editorAnchor = null;
      state.editorHistorical = null;
      if (dialog.open) dialog.close();
      return;
    }
    var anchor = state.activeDraft.anchor;
    if (dialog.open) dialog.close();
    replaceFragmentCard(state.activeDraft.base.fragment_id, anchor);
  }

  function cancelActiveDraft(event) {
    if (event && typeof event.preventDefault === "function") event.preventDefault();
    if (state.activeGlossaryDraft) {
      cancelGlossaryDraft();
      return;
    }
    if (!state.activeDraft || state.saveInProgress) return;
    var anchor = state.activeDraft.anchor;
    var fragmentId = state.activeDraft.base && state.activeDraft.base.fragment_id;
    state.activeDraft = null;
    state.editorBase = null;
    state.editorAnchor = null;
    state.editorHistorical = null;
    var dialog = document.getElementById("alc-editor-dialog");
    if (dialog && dialog.open) dialog.close();
    if (fragmentId) replaceFragmentCard(fragmentId, anchor);
  }

  function cancelGlossaryDraft(force) {
    if (state.saveInProgress && force !== true) return;
    var entryId = state.activeGlossaryDraft &&
      state.activeGlossaryDraft.entryId;
    state.activeGlossaryDraft = null;
    state.editorBase = null;
    state.editorHistorical = null;
    state.editorKind = "fragment";
    clearGlossaryValidationError();
    var dialog = document.getElementById("alc-editor-dialog");
    if (dialog && dialog.open) dialog.close();
    if (entryId) replaceGlossaryRow(entryId);
  }

  function replaceGlossaryRow(entryId) {
    var entry = (state.payload.publication.glossary || []).find(function (item) {
      return glossaryEntryId(item) === entryId;
    });
    var row = document.querySelector(
      '.alc-glossary-row[data-glossary-entry-id="' +
      cssString(entryId) + '"]'
    );
    if (entry && row && typeof row.replaceWith === "function") {
      row.replaceWith(renderGlossaryRow(entry, labels()));
    }
  }

  function replaceFragmentCard(fragmentId, anchor) {
    var current = state.selected.get(fragmentId);
    var card = document.querySelector(
      '.alc-fragment[data-fragment-id="' + cssString(fragmentId) + '"]'
    );
    var row = card && card.closest ? card.closest(".alc-source-row") : null;
    var rowChunk = row ? chunkForTargetId(row.id) : null;
    if (rowChunk && state.renderedChunkIds.has(rowChunk.chunk_id)) {
      rerenderChunk(rowChunk);
      return;
    }
    if (!fragmentIsVisible(current) && card && typeof card.remove === "function") {
      card.remove();
    } else if (current && card && typeof card.replaceWith === "function") {
      card.replaceWith(renderFragment(current));
    }
    if (row) syncSourceBibliographyAlignment(row);
  }

  function historyRevisionLabel(revision, values) {
    var label = "v" + revision.revision;
    var repeated = values.some(function (candidate) {
      return candidate !== revision && candidate.revision === revision.revision;
    });
    return repeated && digestValue(revision.semantic_digest) ?
      label + " · " + revision.semantic_digest.slice(0, 7) : label;
  }

  function renderHistory(fragmentId) {
    var root = document.getElementById("alc-editor-history");
    root.replaceChildren();
    if (!fragmentId) return;
    var strings = labels();
    var revisions = (state.revisions.get(fragmentId) || []).slice().sort(function (a, b) {
      return a.revision - b.revision;
    });
    if (revisions.length <= 1) return;
    var toolbar = element("div", "alc-history-toolbar");
    toolbar.appendChild(element("span", "", strings.history + ": "));
    revisions.forEach(function (revision) {
      var button = element(
        "button", "", historyRevisionLabel(revision, revisions)
      );
      button.type = "button";
      button.classList.toggle(
        "is-selected",
        Boolean(
          state.editorHistorical &&
          state.editorHistorical.semantic_digest === revision.semantic_digest
        )
      );
      button.onclick = function () {
        state.editorHistorical = revision;
        renderHistory(fragmentId);
      };
      toolbar.appendChild(button);
    });
    root.appendChild(toolbar);
    if (!state.editorBase || !state.editorHistorical) return;

    var compare = element("div", "alc-history-compare");
    compare.appendChild(historyPane(
      strings.compareCurrent + " · v" + state.editorBase.revision,
      state.editorBase.markdown_body
    ));
    compare.appendChild(historyPane(
      strings.compareHistorical + " · v" + state.editorHistorical.revision,
      state.editorHistorical.markdown_body
    ));
    root.appendChild(compare);
    var restore = element("button", "alc-history-restore", strings.restore);
    restore.type = "button";
    restore.onclick = restoreHistoricalRevision;
    root.appendChild(restore);
  }

  function renderGlossaryHistory(entryId) {
    var root = document.getElementById("alc-editor-history");
    root.replaceChildren();
    var revisions = (state.glossaryRevisions.get(entryId) || []).slice().sort(function (a, b) {
      return a.revision - b.revision || a.semantic_digest.localeCompare(b.semantic_digest);
    });
    if (!revisions.length) return;
    var base = glossaryBaseEntry(entryId);
    if (!base) return;
    var history = [{
      entry_id: entryId,
      revision: 1,
      entry: base,
      semantic_digest: state.glossaryBaseDigests.get(entryId)
    }].concat(revisions);
    var toolbar = element("div", "alc-history-toolbar");
    toolbar.appendChild(element("span", "", labels().history + ": "));
    history.forEach(function (revision) {
      var button = element(
        "button", "", historyRevisionLabel(revision, history)
      );
      button.type = "button";
      button.classList.toggle(
        "is-selected",
        Boolean(state.editorHistorical &&
          state.editorHistorical.semantic_digest === revision.semantic_digest)
      );
      button.onclick = function () {
        state.editorHistorical = revision;
        renderGlossaryHistory(entryId);
      };
      toolbar.appendChild(button);
    });
    root.appendChild(toolbar);
    if (!state.editorHistorical) return;
    var current = state.selectedGlossary.get(entryId) || base;
    var compare = element("div", "alc-history-compare");
    compare.appendChild(historyPane(
      labels().compareCurrent + " · v" + (state.selectedGlossaryRevisions.get(entryId) || {revision: 1}).revision,
      glossaryHistoryText(current)
    ));
    compare.appendChild(historyPane(
      labels().compareHistorical + " · v" + state.editorHistorical.revision,
      glossaryHistoryText(state.editorHistorical.entry)
    ));
    root.appendChild(compare);
    var restore = element("button", "alc-history-restore", labels().restore);
    restore.type = "button";
    restore.onclick = restoreHistoricalRevision;
    root.appendChild(restore);
  }

  function glossaryHistoryText(entry) {
    return labels().originalTerm + ": " + glossarySourceTerm(entry) + "\n" +
      labels().translatedTerm + ": " + String(entry[glossaryTranslatedKey(entry)] || "") + "\n" +
      labels().definition + ": " + String(entry.definition || "");
  }

  function historyPane(title, markdown) {
    var pane = element("section", "alc-history-pane");
    pane.appendChild(element("h3", "", title));
    pane.appendChild(element("pre", "", markdown || ""));
    return pane;
  }

  function restoreHistoricalRevision() {
    var revision = state.editorHistorical;
    if (!revision) return;
    if (state.activeGlossaryDraft) {
      var historicalEntry = revision.entry;
      var translatedKey = glossaryTranslatedKey(historicalEntry);
      state.activeGlossaryDraft.translated_term = translatedKey ?
        String(historicalEntry[translatedKey] || "") : "";
      state.activeGlossaryDraft.definition = String(historicalEntry.definition || "");
      document.getElementById("alc-editor-title").value =
        state.activeGlossaryDraft.translated_term;
      document.getElementById("alc-editor-markdown").value =
        state.activeGlossaryDraft.definition;
      clearGlossaryValidationError();
      updateDraftSaveButtons();
      markEditorPreviewDirty();
      return;
    }
    if (!state.activeDraft) return;
    state.activeDraft.title = revision.title || null;
    state.activeDraft.role = revision.role;
    state.activeDraft.priority = revision.priority;
    state.activeDraft.markdown_body = revision.markdown_body;
    state.activeDraft.appearance = appearanceForGroup(
      revision.role, revision.priority
    );
    document.getElementById("alc-editor-title").value = revision.title || "";
    var role = document.getElementById("alc-editor-role");
    role.value = revision.role;
    syncCustomSelect(role);
    document.getElementById("alc-editor-priority").value = String(revision.priority);
    document.getElementById("alc-editor-markdown").value = revision.markdown_body;
    syncAppearanceControlsFromDraft();
    updateDraftSaveButtons();
    markEditorPreviewDirty();
  }

  function syncDraftAndSaveState() {
    syncDraftFromDialog();
    updateDraftSaveButtons();
  }

  function syncDraftFromDialog() {
    var dialog = document.getElementById("alc-editor-dialog");
    if (!dialog || !dialog.open) return;
    if (state.activeGlossaryDraft) {
      state.activeGlossaryDraft.translated_term =
        document.getElementById("alc-editor-title").value;
      state.activeGlossaryDraft.definition =
        document.getElementById("alc-editor-markdown").value;
      return;
    }
    if (!state.activeDraft) return;
    state.activeDraft.title =
      document.getElementById("alc-editor-title").value;
    state.activeDraft.role =
      document.getElementById("alc-editor-role").value;
    state.activeDraft.priority =
      document.getElementById("alc-editor-priority").value;
    state.activeDraft.markdown_body =
      document.getElementById("alc-editor-markdown").value;
  }

  function markEditorPreviewDirty() {
    state.editorPreviewDirty = true;
    if (state.editorPreviewTimer !== null) {
      window.clearTimeout(state.editorPreviewTimer);
    }
    state.editorPreviewTimer = window.setTimeout(function () {
      state.editorPreviewTimer = null;
      var dialog = document.getElementById("alc-editor-dialog");
      if (dialog && dialog.open && state.editorPreviewDirty) updatePreview();
    }, 150);
  }

  function updatePreview() {
    var preview = document.getElementById("alc-editor-preview");
    preview.replaceChildren(renderMarkdown(
      document.getElementById("alc-editor-markdown").value
    ));
    if (state.activeDraft) {
      applyFragmentAppearance(
        preview, state.activeDraft.role, state.activeDraft.appearance
      );
    }
    state.editorPreviewDirty = false;
  }

  function saveEditor(event) {
    if (state.activeGlossaryDraft) return persistGlossaryEditor(event);
    return persistEditor(event, false);
  }

  function glossaryEntriesWithReplacement(entry) {
    var entryId = glossaryEntryId(entry);
    return (state.payload.publication.glossary || []).map(function (current) {
      return glossaryEntryId(current) === entryId ? entry : current;
    });
  }

  function applyGlossaryMentionReplacement(markdown, mentions, replacement) {
    var value = normalizeMarkdown(markdown);
    mentions.slice().sort(function (left, right) {
      return right.markdown_start - left.markdown_start ||
        right.markdown_end - left.markdown_end;
    }).forEach(function (mention) {
      if (value.slice(mention.markdown_start, mention.markdown_end) !== mention.surface) {
        throw new Error("glossary mention changed before propagation");
      }
      value = value.slice(0, mention.markdown_start) + replacement +
        value.slice(mention.markdown_end);
    });
    return value;
  }

  function glossaryDefinitionMentionRanges(markdown, surface) {
    var value = normalizeMarkdown(markdown);
    var protectedRanges = glossaryProtectedMarkdownRanges(value);
    var mentions = [];
    var skipped = 0;
    var start = 0;
    while (surface && (start = value.indexOf(surface, start)) >= 0) {
      var end = start + surface.length;
      var protectedHit = protectedRanges.some(function (range) {
        return start < range[1] && range[0] < end;
      });
      if (protectedHit ||
        !glossarySurfaceBoundaryIsSafe(value, start, end, surface)) {
        skipped += 1;
      } else {
        mentions.push({
          markdown_start: start,
          markdown_end: end,
          surface: surface
        });
      }
      start = end;
    }
    return {mentions: mentions, skipped: skipped};
  }

  async function prepareGlossaryPropagation(draft, entry, editedAt) {
    var translatedKey = glossaryTranslatedKey(entry);
    var previousSurface = glossaryTranslatedSurface(draft.base);
    var nextSurface = translatedKey ? glossaryTranslatedSurface(entry) : "";
    if (previousSurface === nextSurface) {
      return {
        revisions: [], glossaryRevisions: [], manifest: null, skipped: 0
      };
    }
    var batchId = "glossary-" + crypto.randomUUID().toLowerCase();
    var currentEntries = state.payload.publication.glossary || [];
    var nextEntries = glossaryEntriesWithReplacement(entry);
    var revisions = [];
    var glossaryRevisions = [];
    var skipped = 0;
    var ambiguousEntryIds = new Set();
    var selected = Array.from(state.selected.values()).sort(function (left, right) {
      return left.fragment_id.localeCompare(right.fragment_id);
    });
    for (var index = 0; index < selected.length; index += 1) {
      var base = selected[index];
      if (!glossaryEntryTargetsFragment(draft.base, base)) continue;
      var indexed = fragmentGlossaryMentions(
        base, currentEntries, draft.entryId
      );
      skipped += indexed.skipped;
      indexed.ambiguous_entry_ids.forEach(function (entryId) {
        ambiguousEntryIds.add(entryId);
      });
      var mentions = indexed.mentions.filter(function (mention) {
        return mention.entry_id === draft.entryId;
      });
      if (!mentions.length) continue;
      assertEditorBaseCurrent(base);
      var markdown = applyGlossaryMentionReplacement(
        base.markdown_body, mentions, nextSurface
      );
      var metadata = metadataOnly(base);
      metadata.revision = base.revision + 1;
      metadata.parent_semantic_digest = base.semantic_digest;
      metadata.provenance = Object.assign({}, metadata.provenance || {}, {
        last_editor: "alc-render-browser",
        edited_at: editedAt,
        reason: "glossary-propagation",
        propagation_batch_id: batchId,
        glossary_entry_id: draft.entryId
      });
      updateGlossaryMentionProvenance(
        metadata.provenance, metadata, markdown, nextEntries, draft.entryId
      );
      validateRevisionMetadata(metadata);
      var digest = await semanticDigest(metadata, markdown);
      var filename = revisionFilename(metadata.revision, digest);
      var path = glossaryBatchFragmentPath(
        batchId, metadata.fragment_id, metadata.revision, digest
      );
      revisions.push({
        metadata: metadata,
        markdown: markdown,
        digest: digest,
        filename: filename,
        path: path,
        encoded: FRONT_BEGIN + "\n" + stableStringify(metadata) + "\n" +
          FRONT_END + "\n" + markdown
      });
    }
    for (var glossaryIndex = 0;
      glossaryIndex < currentEntries.length; glossaryIndex += 1) {
      var peer = currentEntries[glossaryIndex];
      var peerEntryId = glossaryEntryId(peer);
      if (!peerEntryId || peerEntryId === draft.entryId ||
        typeof peer.definition !== "string") continue;
      if (glossaryDefinitionHasForbiddenControl(peer.definition)) {
        skipped += 1;
        continue;
      }
      var definitionMentions = glossaryDefinitionMentionRanges(
        peer.definition, previousSurface
      );
      skipped += definitionMentions.skipped;
      if (!definitionMentions.mentions.length) continue;
      if (!glossaryEntryEditableInState(peer)) {
        throw new Error(
          "glossary definition cannot be propagated safely: " + peerEntryId
        );
      }
      var peerRevision = state.selectedGlossaryRevisions.get(peerEntryId);
      var peerDraft = {
        entryId: peerEntryId,
        baseDigest: selectedGlossaryDigest(peerEntryId),
        baseRevision: peerRevision ? peerRevision.revision : 1
      };
      assertGlossaryBaseCurrent(peerDraft);
      var peerEntry = JSON.parse(JSON.stringify(peer));
      peerEntry.definition = applyGlossaryMentionReplacement(
        peer.definition, definitionMentions.mentions, nextSurface
      );
      var peerMetadata = {
        schema_version: GLOSSARY_REVISION_SCHEMA,
        entry_id: peerEntryId,
        revision: peerDraft.baseRevision + 1,
        parent_semantic_digest: peerDraft.baseDigest,
        entry: peerEntry,
        provenance: {
          producer: "alc-render-browser",
          edited_at: editedAt,
          reason: "glossary-propagation",
          propagation_batch_id: batchId,
          glossary_entry_id: draft.entryId
        }
      };
      validateGlossaryRevisionMetadata(peerMetadata);
      if (!validGlossaryRevisionChange(peer, peerEntry)) {
        throw new Error("glossary propagation changed an immutable peer field");
      }
      var peerDigest = await canonicalDigest(
        glossaryRevisionMaterial(peerMetadata)
      );
      var peerPath = glossaryBatchGlossaryPath(
        batchId, peerMetadata.revision, peerDigest
      );
      glossaryRevisions.push({
        metadata: peerMetadata,
        digest: peerDigest,
        path: peerPath,
        encoded: encodeGlossaryRevision(peerMetadata)
      });
    }
    if (ambiguousEntryIds.has(draft.entryId)) {
      throw new Error(
        "glossary propagation found overlapping term mentions; edit the translation before retrying"
      );
    }
    var manifest = revisions.length || glossaryRevisions.length ? {
      schema_version: GLOSSARY_PROPAGATION_SCHEMA,
      batch_id: batchId,
      fragments: revisions.map(function (item) {
        return {
          path: item.path,
          fragment_id: item.metadata.fragment_id,
          revision: item.metadata.revision,
          parent_semantic_digest: item.metadata.parent_semantic_digest,
          semantic_digest: item.digest
        };
      }),
      glossary_revisions: glossaryRevisions.map(function (item) {
        return {
          path: item.path,
          entry_id: item.metadata.entry_id,
          revision: item.metadata.revision,
          parent_semantic_digest: item.metadata.parent_semantic_digest,
          semantic_digest: item.digest
        };
      })
    } : null;
    if (manifest) validateGlossaryPropagation(manifest);
    return {
      revisions: revisions,
      glossaryRevisions: glossaryRevisions,
      manifest: manifest,
      skipped: skipped
    };
  }

  async function writeGlossaryPropagationBatch(batch) {
    var items = batch.revisions.concat(batch.glossaryRevisions || []);
    for (var index = 0; index < items.length; index += 1) {
      var item = items[index];
      var segments = item.path.split("/");
      var folder = state.directory;
      for (var part = 0; part < segments.length - 1; part += 1) {
        folder = await folder.getDirectoryHandle(segments[part], {create: true});
      }
      await writeImmutableRevision(folder, segments[segments.length - 1], item.encoded);
    }
  }

  async function persistGlossaryEditor(event) {
    if (event && typeof event.preventDefault === "function") event.preventDefault();
    if (state.exportInProgress || state.directorySelectionInProgress) {
      setStatus(labels().revisionBusy, "error");
      return;
    }
    if (state.saveInProgress || !state.activeGlossaryDraft) return;
    syncDraftFromDialog();
    if (!activeGlossaryDraftValid()) {
      showGlossaryValidationError(labels().glossaryTranslatedRequired);
      updateDraftSaveButtons();
      return;
    }
    clearGlossaryValidationError();
    var dialog = document.getElementById("alc-editor-dialog");
    var controls = dialog ? Array.prototype.slice.call(
      dialog.querySelectorAll("button, input, select, textarea")
    ) : [];
    if (typeof document.querySelectorAll === "function") {
      Array.prototype.forEach.call(document.querySelectorAll(
        ".alc-glossary-row.is-inline-editing button, " +
        ".alc-glossary-row.is-inline-editing input, " +
        ".alc-glossary-row.is-inline-editing textarea"
      ), function (control) {
        if (controls.indexOf(control) < 0) controls.push(control);
      });
    }
    var disabledStates = controls.map(function (control) { return control.disabled; });
    state.saveInProgress = true;
    controls.forEach(function (control) { control.disabled = true; });
    try {
      var draft = state.activeGlossaryDraft;
      assertGlossaryBaseCurrent(draft);
      var translatedKey = glossaryTranslatedKey(draft.base);
      var entry = JSON.parse(JSON.stringify(draft.base));
      entry[translatedKey] = String(draft.translated_term || "").normalize("NFC").trim();
      entry.definition = String(draft.definition || "").normalize("NFC").trim();
      if (stableStringify(entry) === stableStringify(draft.base)) {
        cancelGlossaryDraft(true);
        setStatus(labels().glossarySaveUnchanged);
        return;
      }
      if (!state.directory && !await connectDirectory()) return;
      if (!state.directory) return;
      assertGlossaryBaseCurrent(draft);
      loadAllPayload(false);
      var editedAt = new Date().toISOString();
      var propagation = await prepareGlossaryPropagation(draft, entry, editedAt);
      var metadata = {
        schema_version: GLOSSARY_REVISION_SCHEMA,
        entry_id: draft.entryId,
        revision: draft.baseRevision + 1,
        parent_semantic_digest: draft.baseDigest,
        entry: entry,
        provenance: {
          producer: "alc-render-browser",
          edited_at: editedAt
        }
      };
      if (propagation.manifest) {
        metadata.provenance.propagation = propagation.manifest;
      }
      validateGlossaryRevisionMetadata(metadata);
      if (!validGlossaryRevisionChange(draft.base, metadata.entry)) {
        throw new Error("glossary edit changed an immutable field");
      }
      var digest = await canonicalDigest(glossaryRevisionMaterial(metadata));
      var encoded = encodeGlossaryRevision(metadata);
      await writeGlossaryPropagationBatch(propagation);
      var folder = await glossaryDirectory(true);
      await writeImmutableRevision(
        folder, glossaryRevisionFileName(metadata.revision, digest), encoded
      );
      var previousSelected = new Map(state.selected);
      var previousGlossary = new Map(state.selectedGlossary);
      propagation.revisions.forEach(function (item) {
        addRevision(Object.assign({}, item.metadata, {
          markdown_body: item.markdown,
          semantic_digest: item.digest,
          _origin: "directory"
        }));
        resolveOne(item.metadata.fragment_id);
      });
      propagation.glossaryRevisions.forEach(function (item) {
        addGlossaryRevision(Object.assign({}, item.metadata, {
          semantic_digest: item.digest,
          _origin: "directory"
        }));
      });
      addGlossaryRevision(Object.assign({}, metadata, {
        semantic_digest: digest,
        _origin: "directory"
      }));
      resolveGlossaryAll();
      state.payload.glossary_revisions = glossaryRevisionState().revisions;
      state.activeGlossaryDraft = null;
      state.editorBase = null;
      state.editorHistorical = null;
      state.editorKind = "fragment";
      if (dialog && dialog.open) dialog.close();
      refreshChangedSelections(previousSelected);
      refreshGlossarySurfaces(previousGlossary);
      setStatus(labels().glossarySaveSuccess);
    } catch (error) {
      setStatus(String(error.message || error), "error");
    } finally {
      state.saveInProgress = false;
      controls.forEach(function (control, index) {
        control.disabled = disabledStates[index];
      });
    }
  }

  function deleteEditor(event) {
    if (event && typeof event.preventDefault === "function") event.preventDefault();
    if (!state.activeDraft || !state.activeDraft.base) return;
    if (!window.confirm(labels().deleteConfirm)) return;
    return persistEditor(event, true);
  }

  async function persistEditor(event, forceDelete) {
    if (event && typeof event.preventDefault === "function") event.preventDefault();
    if (state.exportInProgress || state.directorySelectionInProgress) {
      setStatus(labels().revisionBusy, "error");
      return;
    }
    if (state.saveInProgress || !state.activeDraft) return;
    syncDraftFromDialog();
    var saveButton = document.getElementById("alc-editor-save");
    var dialog = document.getElementById("alc-editor-dialog");
    var controls = dialog ? Array.prototype.slice.call(
      dialog.querySelectorAll("button, input, select, textarea")
    ) : [];
    if (typeof document.querySelectorAll === "function") {
      Array.prototype.forEach.call(document.querySelectorAll(
        ".alc-inline-editor button, .alc-inline-editor textarea, " +
        ".alc-inline-actions button"
      ), function (control) {
        if (controls.indexOf(control) < 0) controls.push(control);
      });
    }
    var disabledStates = controls.map(function (control) {
      return control.disabled;
    });
    state.saveInProgress = true;
    controls.forEach(function (control) { control.disabled = true; });
    if (saveButton) saveButton.disabled = true;
    try {
      var draft = state.activeDraft;
      var base = draft.base;
      var editorGeneration = state.editorGeneration;
      var editorAnchor = JSON.parse(JSON.stringify(draft.anchor));
      var editable = editableDraftState(draft);
      var deleting = Boolean(forceDelete || emptyNoteState(editable));
      var revisionEditable = deleting ? Object.assign({}, editable, {
        title: null,
        markdown_body: "",
        citation_ids: []
      }) : editable;
      assertKnownCitations(revisionEditable.citation_ids);
      if (base) assertEditorBaseCurrent(base);
      if (
        base && !deleting &&
        stableStringify(editable) ===
          stableStringify(editableRevisionState(base))
      ) {
        finishActiveDraft(base.fragment_id, editorAnchor, editorGeneration);
        setStatus(labels().saveUnchanged);
        return;
      }
      if (!state.directory) {
        if (!await connectDirectory()) return;
      }
      if (!state.directory) return;
      if (base) assertEditorBaseCurrent(base);
      var metadata = base ? metadataOnly(base) : newNoteMetadata(editorAnchor);
      metadata.schema_version = FRAGMENT_SCHEMA;
      metadata.appearance = revisionEditable.appearance;
      metadata.deleted = deleting;
      metadata.revision = base ? base.revision + 1 : 1;
      metadata.parent_semantic_digest = base ? base.semantic_digest : null;
      metadata.title = revisionEditable.title;
      metadata.role = revisionEditable.role;
      metadata.priority = revisionEditable.priority;
      metadata.citation_ids = revisionEditable.citation_ids;
      metadata.provenance = Object.assign({}, metadata.provenance || {}, {
        last_editor: "alc-render-browser",
        edited_at: new Date().toISOString(),
        appearance_scope: "role_priority"
      });
      updateGlossaryMentionProvenance(
        metadata.provenance, metadata, revisionEditable.markdown_body,
        state.payload.publication.glossary || []
      );
      validateRevisionMetadata(metadata);
      var digest = await semanticDigest(metadata, revisionEditable.markdown_body);
      var encoded = FRONT_BEGIN + "\n" + stableStringify(metadata) + "\n" +
        FRONT_END + "\n" + revisionEditable.markdown_body;
      var filename = revisionFilename(metadata.revision, digest);
      var folder = await fragmentsDirectory(true);
      await writeImmutableRevision(folder, filename, encoded);
      var revision = Object.assign({}, metadata, {
        markdown_body: revisionEditable.markdown_body,
        semantic_digest: digest,
        _origin: "directory"
      });
      state.activeDraft = null;
      state.editorBase = null;
      state.editorAnchor = null;
      state.editorHistorical = null;
      var uiError = null;
      try {
        addRevision(revision);
        resolveOne(revision.fragment_id);
        refreshFragmentGroup(revision.fragment_id, revision.anchor);
        if (!deleting) state.hiddenRoles.delete(revision.role);
        syncVisibilityRoles();
        if (state.visibilityReady) renderVisibilityOptions();
      } catch (error) {
        uiError = error;
      }
      try {
        refreshChunkForAnchor(revision.anchor);
      } catch (error) {
        uiError = uiError || error;
      }
      if (state.editorGeneration === editorGeneration) {
        try {
          if (dialog && dialog.open) dialog.close();
        } catch (error) {
          uiError = uiError || error;
        }
      }
      if (uiError && base) {
        try {
          replaceFragmentCard(revision.fragment_id, revision.anchor);
        } catch (_replaceError) {
          /* The saved revision and original UI error remain authoritative. */
        }
      }
      if (uiError) {
        try {
          updateFragmentGroup(revision.fragment_id, revision.anchor);
          rerenderChunk(chunkForAnchor(revision.anchor));
        } catch (_recoveryError) {
          /* The status below reports the first post-commit UI error. */
        }
      }
      setStatus(
        (deleting ? labels().deleteSuccess : labels().saveSuccess) +
          (uiError ? " " + String(uiError.message || uiError) : "")
      );
    } catch (error) {
      setStatus(String(error.message || error), "error");
    } finally {
      state.saveInProgress = false;
      controls.forEach(function (control, index) {
        control.disabled = disabledStates[index];
      });
    }
  }

  function emptyNoteState(editable) {
    return editable.role === "note" && editable.title === null &&
      !editable.markdown_body.trim();
  }

  function editableDraftState(draft) {
    var markdown = normalizeMarkdown(draft.markdown_body);
    var priority = Number(draft.priority);
    if (!Number.isInteger(priority) || priority < 1) {
      throw new Error("priority must be a positive integer");
    }
    return {
      title: String(draft.title || "").normalize("NFC").trim() || null,
      markdown_body: markdown,
      role: String(draft.role || ""),
      priority: priority,
      citation_ids: citationIds(markdown),
      appearance: normalizeAppearance(draft.appearance)
    };
  }

  function editableRevisionState(revision) {
    var markdown = normalizeMarkdown(revision.markdown_body);
    return {
      title: String(revision.title || "").normalize("NFC").trim() || null,
      markdown_body: markdown,
      role: revision.role,
      priority: revision.priority,
      citation_ids: citationIds(markdown),
      appearance: appearanceForGroup(revision.role, revision.priority)
    };
  }

  function activeDraftHasChanges() {
    if (state.activeGlossaryDraft) {
      var draft = state.activeGlossaryDraft;
      var baseKey = glossaryTranslatedKey(draft.base);
      return String(draft.translated_term || "") !==
        String(draft.base[baseKey] || "") ||
        String(draft.definition || "") !== String(draft.base.definition || "");
    }
    var draft = state.activeDraft;
    if (!draft) return false;
    try {
      if (!draft.base) {
        return stableStringify(editableDraftState(draft)) !== stableStringify({
          title: null,
          markdown_body: normalizeMarkdown(""),
          role: "note",
          priority: 110,
          citation_ids: [],
          appearance: null
        });
      }
      return stableStringify(editableDraftState(draft)) !==
        stableStringify(editableRevisionState(draft.base));
    } catch (_error) {
      return true;
    }
  }

  function activeGlossaryDraftValid() {
    return !state.activeGlossaryDraft || Boolean(
      String(state.activeGlossaryDraft.translated_term || "")
        .normalize("NFC").trim()
    );
  }

  function clearGlossaryValidationError() {
    if (typeof document === "undefined") return;
    var error = document.getElementById("alc-editor-error");
    if (error) {
      error.textContent = "";
      error.hidden = true;
    }
    var controls = [];
    var advanced = document.getElementById("alc-editor-title");
    if (advanced) controls.push(advanced);
    if (typeof document.querySelectorAll === "function") {
      Array.prototype.forEach.call(
        document.querySelectorAll(".alc-glossary-inline-input"),
        function (control) { controls.push(control); }
      );
    }
    controls.forEach(function (control) {
      if (typeof control.removeAttribute === "function") {
        control.removeAttribute("aria-invalid");
      }
    });
    var status = document.getElementById("alc-storage-status");
    if (status && status.dataset.glossaryValidation === "true") {
      setStatus("");
    }
  }

  function showGlossaryValidationError(message) {
    if (typeof document === "undefined") return;
    var dialog = document.getElementById("alc-editor-dialog");
    var advanced = Boolean(dialog && dialog.open);
    var control = null;
    if (advanced) {
      var error = document.getElementById("alc-editor-error");
      if (error) {
        error.textContent = message;
        error.hidden = false;
      }
      control = document.getElementById("alc-editor-title");
    } else {
      setStatus(message, "error");
      var status = document.getElementById("alc-storage-status");
      if (status) status.dataset.glossaryValidation = "true";
      if (typeof document.querySelector === "function") {
        control = document.querySelector(
          '.alc-glossary-row[data-glossary-entry-id="' +
          cssString(state.activeGlossaryDraft.entryId) +
          '"] .alc-glossary-inline-input'
        );
      }
    }
    if (control) {
      if (typeof control.setAttribute === "function") {
        control.setAttribute("aria-invalid", "true");
      }
      if (typeof control.focus === "function") control.focus();
    }
  }

  function updateDraftSaveButtons(scope) {
    var disabled = !appearanceControlsValid() || !activeDraftHasChanges() ||
      state.saveInProgress;
    var dialogSave = document.getElementById("alc-editor-save");
    if (dialogSave) dialogSave.disabled = disabled;
    var localSave = scope && typeof scope.querySelector === "function" ?
      scope.querySelector(".alc-inline-save") : null;
    if (localSave) localSave.disabled = disabled;
    if (typeof document.querySelectorAll !== "function") return;
    Array.prototype.forEach.call(
      document.querySelectorAll(".alc-inline-save"),
      function (button) { button.disabled = disabled; }
    );
  }

  function assertEditorBaseCurrent(base) {
    var current = state.selected.get(base.fragment_id);
    var nextChildren = (
      state.revisions.get(base.fragment_id) || []
    ).filter(function (revision) {
      return revision.parent_semantic_digest === base.semantic_digest &&
        revision.revision === base.revision + 1;
    });
    if (
      !current ||
      current.semantic_digest !== base.semantic_digest ||
      nextChildren.length > 0
    ) {
      throw new Error(labels().historyChanged);
    }
  }

  function assertGlossaryBaseCurrent(draft) {
    var nextChildren = draft ? (
      state.glossaryRevisions.get(draft.entryId) || []
    ).filter(function (revision) {
      return revision.parent_semantic_digest === draft.baseDigest &&
        revision.revision === draft.baseRevision + 1;
    }) : [];
    if (!draft || selectedGlossaryDigest(draft.entryId) !== draft.baseDigest ||
      nextChildren.length > 0) {
      throw new Error(labels().glossaryHistoryChanged);
    }
  }

  function finishActiveDraft(fragmentId, anchor, editorGeneration) {
    state.activeDraft = null;
    state.editorBase = null;
    state.editorAnchor = null;
    state.editorHistorical = null;
    var dialog = document.getElementById("alc-editor-dialog");
    if (
      dialog &&
      dialog.open &&
      state.editorGeneration === editorGeneration
    ) {
      dialog.close();
    }
    replaceFragmentCard(fragmentId, anchor);
  }

  async function writeImmutableRevision(folder, filename, encoded) {
    var existing = null;
    try {
      existing = await folder.getFileHandle(filename);
    } catch (error) {
      if (error.name !== "NotFoundError") throw error;
    }
    if (existing) {
      if (await revisionFileMatches(existing, encoded)) return;
      throw new Error("revision file already exists; no file was overwritten");
    }
    var handle = await folder.getFileHandle(filename, {create: true});
    var created = await handle.getFile();
    if (created.size > 0) {
      if (await created.text() === encoded) return;
      throw new Error("revision file already exists; no file was overwritten");
    }
    var writable = await handle.createWritable();
    try {
      await writable.write(encoded);
      await writable.close();
    } catch (error) {
      if (await revisionFileMatches(handle, encoded)) return;
      if (typeof writable.abort === "function") {
        try {
          await writable.abort();
        } catch (_abortError) {
          /* The original write error is the useful failure. */
        }
      }
      throw error;
    }
    if (!await revisionFileMatches(handle, encoded)) {
      throw new Error("saved revision bytes could not be verified");
    }
  }

  async function revisionFileMatches(handle, encoded) {
    try {
      return await (await handle.getFile()).text() === encoded;
    } catch (_error) {
      return false;
    }
  }

  function revisionFilename(revision, digest) {
    return "revision-" + String(revision).padStart(6, "0") +
      "-" + digest + ".md";
  }

  function metadataOnly(revision) {
    var keys = [
      "schema_version", "source", "fragment_id", "revision",
      "parent_semantic_digest", "anchor", "priority", "role", "language",
      "title", "citation_ids", "provenance"
    ];
    keys.push("appearance", "deleted");
    var value = {};
    keys.forEach(function (key) { value[key] = revision[key]; });
    return JSON.parse(JSON.stringify(value));
  }

  function newNoteMetadata(anchor) {
    var publication = state.payload.publication;
    var profile = publication.reader_profile || {};
    return {
      schema_version: FRAGMENT_SCHEMA,
      source: state.payload.source_identity,
      fragment_id: "user-" + crypto.randomUUID().toLowerCase(),
      revision: 1,
      parent_semantic_digest: null,
      anchor: anchor,
      priority: 110,
      role: "note",
      language: profile.target_language || profile.source_language || "und",
      title: null,
      citation_ids: [],
      appearance: null,
      deleted: false,
      provenance: {
        producer: "alc-render-browser",
        created_at: new Date().toISOString()
      }
    };
  }

  function anchorBlock(block) {
    var fingerprints = state.payload.block_fingerprints || {};
    return {
      block_id: block.block_id,
      kind: block.kind,
      ordinal: block.ordinal,
      locator: block.locator,
      content_fingerprint: fingerprints[block.block_id]
    };
  }

  function citationIds(markdown) {
    var values = [];
    var seen = new Set();
    var pattern = /\[@([A-Za-z0-9][A-Za-z0-9._:-]*)\]/g;
    var match;
    while ((match = pattern.exec(markdown))) {
      if (!seen.has(match[1])) {
        seen.add(match[1]);
        values.push(match[1]);
      }
    }
    return values;
  }

  function bibliographyIdSet() {
    var values = new Set();
    (state.payload.publication.bibliography || []).forEach(function (item) {
      var id = item.evidence_id || item.citation_id || item.id;
      if (typeof id === "string" && id) values.add(id);
    });
    return values;
  }

  function assertKnownCitations(citations) {
    var known = bibliographyIdSet();
    var unknown = citations.find(function (citation) {
      return !known.has(citation);
    });
    if (unknown !== undefined) {
      throw new Error(labels().unknownCitation + unknown);
    }
  }

  async function fragmentsDirectory(create) {
    return state.directory.getDirectoryHandle(
      "fragments", {create: Boolean(create)}
    );
  }

  async function glossaryDirectory(create) {
    return state.directory.getDirectoryHandle(
      "glossary", {create: Boolean(create)}
    );
  }

  async function parseRevisionFile(value, filename) {
    var prefix = FRONT_BEGIN + "\n";
    var separator = "\n" + FRONT_END + "\n";
    if (value.slice(0, prefix.length) !== prefix) {
      throw new Error("missing JSON front matter");
    }
    var split = value.indexOf(separator, prefix.length);
    if (split < 0) throw new Error("unterminated JSON front matter");
    var metadata = JSON.parse(value.slice(prefix.length, split));
    if (stableStringify(metadata) !== value.slice(prefix.length, split)) {
      throw new Error("JSON front matter is not canonical or has duplicate keys");
    }
    loadPayloadForRevisionMetadata(metadata);
    validateRevisionMetadata(metadata);
    var markdown = normalizeMarkdown(value.slice(split + separator.length));
    var digest = await semanticDigest(metadata, markdown);
    var expected = /^revision-([0-9]{6,})-([0-9a-f]{64})[.]md$/.exec(filename);
    if (!expected || Number(expected[1]) !== metadata.revision || expected[2] !== digest) {
      throw new Error("filename identity does not match content");
    }
    return Object.assign({}, metadata, {
      markdown_body: markdown,
      semantic_digest: digest
    });
  }

  async function parseGlossaryRevisionFile(value, filename) {
    var metadata;
    var markdownEnvelope = typeof value === "string" &&
      value.slice(0, GLOSSARY_FRONT_BEGIN.length + 1) ===
        GLOSSARY_FRONT_BEGIN + "\n";
    if (markdownEnvelope) {
      var prefix = GLOSSARY_FRONT_BEGIN + "\n";
      var separator = "\n" + GLOSSARY_FRONT_END + "\n";
      var split = value.indexOf(separator, prefix.length);
      if (split < 0) {
        throw new Error("glossary revision has unterminated JSON front matter");
      }
      var metadataText = value.slice(prefix.length, split);
      try {
        metadata = JSON.parse(metadataText);
      } catch (_error) {
        throw new Error("glossary revision front matter is not valid JSON");
      }
      if (stableStringify(metadata) !== metadataText) {
        throw new Error("glossary revision front matter is not canonical");
      }
      if (!plainObject(metadata.entry) ||
        Object.prototype.hasOwnProperty.call(metadata.entry, "definition")) {
        throw new Error("glossary revision front matter entry is invalid");
      }
      metadata.entry.definition = normalizeMarkdown(
        value.slice(split + separator.length)
      );
      if (!filename.endsWith(".md")) {
        throw new Error("glossary revision filename has the wrong format extension");
      }
    } else {
      if (typeof value !== "string" || !value.endsWith("\n")) {
        throw new Error("legacy glossary revision JSON must end with a newline");
      }
      try {
        metadata = JSON.parse(value.slice(0, -1));
      } catch (_error) {
        throw new Error("glossary revision JSON is invalid");
      }
      if (stableStringify(metadata) !== value.slice(0, -1)) {
        throw new Error("glossary revision JSON is not canonical");
      }
      if (!filename.endsWith(".json")) {
        throw new Error("glossary revision filename has the wrong format extension");
      }
    }
    validateGlossaryRevisionMetadata(metadata);
    var digest = await canonicalDigest(glossaryRevisionMaterial(metadata));
    var expected = /^revision-([0-9]{6,})-([0-9a-f]{64})[.](?:md|json)$/.exec(
      filename
    );
    if (
      !expected || Number(expected[1]) !== metadata.revision ||
      expected[2] !== digest
    ) {
      throw new Error("filename identity does not match glossary content");
    }
    return Object.assign({}, metadata, {semantic_digest: digest});
  }

  function loadPayloadForRevisionMetadata(metadata) {
    if (state.payloadVersion !== "v2" || !plainObject(metadata)) return;
    ensureSourceIndexes();
    if (
      metadata.schema_version !== FRAGMENT_SCHEMA ||
      !plainObject(metadata.source) ||
      stableStringify(metadata.source) !== state.sourceIdentityJson
    ) {
      return;
    }
    var anchor = metadata.anchor;
    if (!plainObject(anchor) || !Array.isArray(anchor.related_blocks)) return;
    if (!anchor.related_blocks.every(function (frozen) {
      return plainObject(frozen) && normalizedNonblank(frozen.block_id);
    })) return;
    var descriptors = new Map();
    anchor.related_blocks.forEach(function (frozen) {
      var blockId = frozen && frozen.block_id;
      if (!normalizedNonblank(blockId)) return;
      var descriptor = state.payloadChunkByBlockId.get(blockId);
      if (descriptor && normalizedNonblank(descriptor.chunk_id)) {
        descriptors.set(descriptor.chunk_id, descriptor);
      }
    });
    descriptors.forEach(loadPayloadChunk);
  }

  async function semanticDigest(metadata, markdown) {
    if (!crypto.subtle) throw new Error("Web Crypto is required to save revisions");
    var material = stableStringify({
      metadata: metadata,
      markdown_body: normalizeMarkdown(markdown)
    });
    var bytes = new TextEncoder().encode(material);
    var digest = await crypto.subtle.digest("SHA-256", bytes);
    return Array.from(new Uint8Array(digest)).map(function (value) {
      return value.toString(16).padStart(2, "0");
    }).join("");
  }

  function validateRevisionMetadata(metadata) {
    ensureSourceIndexes();
    validateCurrentSourceIdentity();
    var fields = [
      "anchor", "citation_ids", "fragment_id", "language",
      "parent_semantic_digest", "priority", "provenance", "revision", "role",
      "schema_version", "source", "title"
    ];
    fields.push("appearance", "deleted");
    requireExactObject(metadata, fields, "fragment revision");
    validateIntegerJson(metadata, "fragment revision");
    if (
      metadata.schema_version !== FRAGMENT_SCHEMA ||
      !portableIdentifier(metadata.fragment_id) ||
      !positiveInteger(metadata.revision) ||
      !positiveInteger(metadata.priority) ||
      !normalizedNonblank(metadata.role) ||
      !normalizedNonblank(metadata.language) ||
      (
        metadata.title !== null &&
        !normalizedNonblank(metadata.title)
      )
    ) {
      throw new Error("fragment revision metadata is invalid");
    }
    if (
      (metadata.revision === 1 && metadata.parent_semantic_digest !== null) ||
      (metadata.revision > 1 &&
        !/^[0-9a-f]{64}$/.test(metadata.parent_semantic_digest || ""))
    ) {
      throw new Error("fragment revision parent identity is invalid");
    }
    if (stableStringify(metadata.source) !== state.sourceIdentityJson) {
      throw new Error("fragment revision binds another rich source");
    }
    validateAnchor(metadata.anchor);
    if (!Array.isArray(metadata.citation_ids)) {
      throw new Error("fragment citation_ids must be an array");
    }
    var citationSet = new Set();
    metadata.citation_ids.forEach(function (citation) {
      if (!normalizedNonblank(citation) || citationSet.has(citation)) {
        throw new Error("fragment citation IDs must be unique non-empty strings");
      }
      citationSet.add(citation);
    });
    if (!plainObject(metadata.provenance)) {
      throw new Error("fragment provenance must be an object");
    }
    normalizeAppearance(metadata.appearance);
    if (typeof metadata.deleted !== "boolean") {
      throw new Error("fragment deleted flag must be a boolean");
    }
  }

  function validateCurrentSourceIdentity() {
    if (state.sourceIdentityValidatedPayload === state.payload) return;
    validateSourceIdentity(state.payload.source_identity);
    state.sourceIdentityValidatedPayload = state.payload;
  }

  function validateSourceIdentity(source) {
    requireExactObject(source, [
      "artifact_digest", "media_type", "rich_document_digest",
      "size", "source_format"
    ], "source identity");
    if (
      !["html", "markdown", "tex"].includes(source.source_format) ||
      typeof source.media_type !== "string" ||
      source.media_type !== source.media_type.trim().toLowerCase() ||
      source.media_type.indexOf("/") < 1 ||
      source.media_type.indexOf(";") >= 0 ||
      !digestValue(source.artifact_digest) ||
      !digestValue(source.rich_document_digest) ||
      !nonnegativeInteger(source.size)
    ) {
      throw new Error("fragment source identity is invalid");
    }
  }

  function validateAnchor(anchor) {
    requireExactObject(
      anchor, ["kind", "related_blocks", "target_id"], "fragment anchor"
    );
    if (
      !["block", "section"].includes(anchor.kind) ||
      !normalizedNonblank(anchor.target_id) ||
      !Array.isArray(anchor.related_blocks)
    ) {
      throw new Error("fragment anchor is invalid");
    }
    var indexes = ensureSourceIndexes();
    var blocks = indexes.blocksById;
    var sections = indexes.sectionsById;
    if (
      (anchor.kind === "block" && !blocks.has(anchor.target_id)) ||
      (anchor.kind === "section" && !sections.has(anchor.target_id))
    ) {
      throw new Error("fragment anchor target is absent from the rich source");
    }
    var blockIds = new Set();
    var ordinals = new Set();
    anchor.related_blocks.forEach(function (frozen) {
      requireExactObject(frozen, [
        "block_id", "content_fingerprint", "kind", "locator", "ordinal"
      ], "anchor related block");
      if (
        !normalizedNonblank(frozen.block_id) ||
        !["heading", "paragraph", "list", "code", "equation", "table", "figure"]
          .includes(frozen.kind) ||
        !nonnegativeInteger(frozen.ordinal) ||
        !plainObject(frozen.locator) ||
        !digestValue(frozen.content_fingerprint) ||
        blockIds.has(frozen.block_id) ||
        ordinals.has(frozen.ordinal)
      ) {
        throw new Error("anchor related block provenance is invalid");
      }
      var current = blocks.get(frozen.block_id);
      if (
        !current ||
        current.kind !== frozen.kind ||
        current.ordinal !== frozen.ordinal ||
        stableStringify(current.locator) !== stableStringify(frozen.locator) ||
        (state.payload.block_fingerprints || {})[frozen.block_id] !==
          frozen.content_fingerprint
      ) {
        throw new Error("anchor related block differs from the rich source");
      }
      blockIds.add(frozen.block_id);
      ordinals.add(frozen.ordinal);
    });
    if (anchor.kind === "block" && !blockIds.has(anchor.target_id)) {
      throw new Error("block anchor target must be a related block");
    }
  }

  function validateIntegerJson(value, description) {
    if (typeof value === "number") {
      if (!Number.isSafeInteger(value)) {
        throw new Error(description + " contains a non-integer JSON number");
      }
      return;
    }
    if (value === null || ["string", "boolean"].includes(typeof value)) return;
    if (Array.isArray(value)) {
      value.forEach(function (item) { validateIntegerJson(item, description); });
      return;
    }
    if (plainObject(value)) {
      Object.keys(value).forEach(function (key) {
        validateIntegerJson(value[key], description);
      });
      return;
    }
    throw new Error(description + " is not JSON-compatible");
  }

  function validateJsonCompatible(value, description) {
    if (typeof value === "number") {
      if (!Number.isFinite(value)) {
        throw new Error(description + " contains a non-finite JSON number");
      }
      return;
    }
    if (value === null || ["string", "boolean"].includes(typeof value)) return;
    if (Array.isArray(value)) {
      value.forEach(function (item) {
        validateJsonCompatible(item, description);
      });
      return;
    }
    if (plainObject(value)) {
      Object.keys(value).forEach(function (key) {
        validateJsonCompatible(value[key], description);
      });
      return;
    }
    throw new Error(description + " is not JSON-compatible");
  }

  function jsonValuesEqual(left, right) {
    if (left === right) return true;
    if (left === null || right === null || typeof left !== typeof right) {
      return false;
    }
    if (Array.isArray(left) || Array.isArray(right)) {
      return Array.isArray(left) && Array.isArray(right) &&
        left.length === right.length && left.every(function (item, index) {
          return jsonValuesEqual(item, right[index]);
        });
    }
    if (!plainObject(left) || !plainObject(right)) return false;
    var leftKeys = Object.keys(left).sort();
    var rightKeys = Object.keys(right).sort();
    return leftKeys.length === rightKeys.length &&
      leftKeys.every(function (key, index) {
        return key === rightKeys[index] &&
          jsonValuesEqual(left[key], right[key]);
      });
  }

  function requireExactObject(value, fields, description) {
    if (
      !plainObject(value) ||
      stableStringify(Object.keys(value).sort()) !==
        stableStringify(fields.slice().sort())
    ) {
      throw new Error(description + " has invalid fields");
    }
  }

  function plainObject(value) {
    return Boolean(value) && typeof value === "object" && !Array.isArray(value);
  }

  function normalizedNonblank(value) {
    return typeof value === "string" && Boolean(value) && value === value.trim();
  }

  function portableIdentifier(value) {
    return normalizedNonblank(value) &&
      /^[A-Za-z0-9][A-Za-z0-9._:-]*$/.test(value);
  }

  function digestValue(value) {
    return typeof value === "string" && /^[0-9a-f]{64}$/.test(value);
  }

  function positiveInteger(value) {
    return Number.isSafeInteger(value) && value >= 1;
  }

  function nonnegativeInteger(value) {
    return Number.isSafeInteger(value) && value >= 0;
  }

  function stableStringify(value) {
    if (typeof value === "number" && !Number.isSafeInteger(value)) {
      throw new Error("canonical JSON contains a non-integer number");
    }
    if (value === null || typeof value !== "object") {
      var primitive = JSON.stringify(value);
      if (primitive === undefined) throw new Error("value is not JSON-compatible");
      return primitive;
    }
    if (Array.isArray(value)) {
      return "[" + value.map(stableStringify).join(",") + "]";
    }
    return "{" + Object.keys(value).sort().map(function (key) {
      return JSON.stringify(key) + ":" + stableStringify(value[key]);
    }).join(",") + "}";
  }

  function safeToken(value) {
    return String(value).replace(/[^A-Za-z0-9_.:-]/g, "-");
  }

  function setStatus(value, kind) {
    var status = document.getElementById("alc-storage-status");
    if (state.statusTimer !== null) {
      window.clearTimeout(state.statusTimer);
      state.statusTimer = null;
    }
    delete status.dataset.glossaryValidation;
    status.textContent = value || "";
    status.dataset.kind = kind || "info";
    status.hidden = !value;
    if (typeof status.setAttribute === "function") {
      status.setAttribute("role", kind === "error" ? "alert" : "status");
      status.setAttribute("aria-live", kind === "error" ? "assertive" : "polite");
    }
    if (!value) return;
    var timer = window.setTimeout(function () {
      if (state.statusTimer !== timer) return;
      state.statusTimer = null;
      status.textContent = "";
      status.hidden = true;
      delete status.dataset.glossaryValidation;
    }, STATUS_EXPIRY_MS);
    state.statusTimer = timer;
    if (timer && typeof timer.unref === "function") timer.unref();
  }

  function openDatabase() {
    return new Promise(function (resolve, reject) {
      var request = indexedDB.open("alc-render", 1);
      request.onupgradeneeded = function () {
        if (!request.result.objectStoreNames.contains("handles")) {
          request.result.createObjectStore("handles");
        }
      };
      request.onsuccess = function () { resolve(request.result); };
      request.onerror = function () { reject(request.error); };
    });
  }

  function directoryHandleKey() {
    var identity = state.payload && state.payload.source_identity;
    return identity ? "source:" + stableStringify(identity) : null;
  }

  async function rememberDirectoryHandle(handle) {
    try {
      var key = directoryHandleKey();
      if (!key) return;
      var database = await openDatabase();
      var transaction = database.transaction("handles", "readwrite");
      transaction.objectStore("handles").put(handle, key);
    } catch (_error) {
      /* Handle persistence is a convenience, never a reading requirement. */
    }
  }

  async function restoreDirectoryHandle() {
    try {
      var key = directoryHandleKey();
      if (!key) return;
      var database = await openDatabase();
      var transaction = database.transaction("handles", "readonly");
      var handle = await new Promise(function (resolve, reject) {
        var request = transaction.objectStore("handles").get(key);
        request.onsuccess = function () { resolve(request.result); };
        request.onerror = function () { reject(request.error); };
      });
      if (!handle) return;
      var permission = await handle.queryPermission({mode: "readwrite"});
      if (permission === "granted") {
        if (await loadDirectoryRevisions(handle)) {
          updateDirectoryControl();
          setStatus(labels().connected);
        }
      }
    } catch (_error) {
      state.directory = null;
      /* Opaque file origins may not persist IndexedDB; reconnect still works. */
    }
  }

  async function initialize() {
    try {
      state.exportStandaloneSupported = !document.querySelector(
        'script[src], link[rel~="stylesheet"][href]'
      );
      document.body.dataset.alcRenderReady = "loading";
      document.body.dataset.alcRenderComplete = "false";
      state.payload = readPayload();
      setupMarkdown();
      await prepareGlossary();
      initialRevisions();
      captureInitialSelection();
      captureInitialGlossarySelection();
      setupCustomSelectEvents();
      setupReaderSettings();
      renderReader();
      setupVisibility();
      setupSpeech();
      setupTooltip();
      await setupEditor();
      setupExport();
      if (document.fonts && document.fonts.ready) await document.fonts.ready;
      await Promise.all(Array.prototype.slice.call(document.images).map(function (image) {
        if (image.complete) return Promise.resolve();
        if (typeof image.decode === "function") return image.decode().catch(function () {});
        return new Promise(function (resolve) {
          image.addEventListener("load", resolve, {once: true});
          image.addEventListener("error", resolve, {once: true});
        });
      }));
      activateHashTarget(window.location.hash, false);
      document.body.dataset.alcRenderReady = "true";
      startProgressiveRendering();
    } catch (error) {
      stopProgressiveRendering();
      document.body.dataset.alcRenderReady = "error";
      var root = document.getElementById("ac-document") || document.body;
      root.prepend(element("p", "alc-diagnostic", String(error.message || error)));
      throw error;
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initialize, {once: true});
  } else {
    initialize();
  }
}());
