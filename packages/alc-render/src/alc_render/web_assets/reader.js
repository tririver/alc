(function () {
  "use strict";

  var FRONT_BEGIN = "<!-- ALC:FRAGMENT-JSON:BEGIN -->";
  var FRONT_END = "<!-- ALC:FRAGMENT-JSON:END -->";
  var FRAGMENT_SCHEMA = "alc.render.fragment_revision.v3";
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
    width: 100
  };
  var customSelectRegistry = new WeakMap();
  var customSelectSerial = 0;
  var MAX_BLOCKS_PER_RENDER_CHUNK = 36;
  var CHUNK_BLOCK_HEIGHT_ESTIMATE = 220;
  var DIRECTORY_READ_CONCURRENCY = 8;
  var STATUS_EXPIRY_MS = 10000;
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
    saveInProgress: false,
    exportInProgress: false,
    activeDraft: null,
    editorGeneration: 0,
    editorPreviewDirty: true,
    editorPreviewTimer: null,
    statusTimer: null,
    editorBase: null,
    editorAnchor: null,
    editorHistorical: null,
    bibliographyIndexCache: null,
    glossarySurfaceCache: {source: null, target: null},
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
    var language = String(
      (publication.reader_profile || {}).target_language || ""
    ).toLowerCase();
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
      colors: traditional ? "同類型與優先級的顏色" : "同类型与优先级的颜色",
      foreground: traditional ? "前景色" : "前景色",
      background: traditional ? "背景色" : "背景色",
      roleDefaultColors: traditional ? "恢復類型預設" : "恢复类型默认",
      resizeContents: traditional ? "調整目錄寬度" : "调整目录宽度",
      advanced: "预览与更多设置",
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
      references: "参考文献",
      originalTerm: "原文术语",
      translatedTerm: traditional ? "譯文" : "译文",
      definition: "释义",
      view: "显示",
      showLayers: "显示内容",
      original: "原文",
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
      markdownScope: "Markdown 内容",
      allLatest: "全部最新版",
      changedLatest: "仅最新版改动",
      noExportChanges: "没有可导出的改动",
      fullHtml: "全文 => 单个 HTML",
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
      saveBeforeExit: "你已修改当前内容。可以保存修改并退出，也可以不保存直接退出。",
      discardChanges: "不保存",
      saveChanges: "保存修改",
      continueEditing: "继续编辑",
      saveFailedInEditor: "未能完成保存。修改仍保留在编辑区，请检查页面提示后重试。",
      editContent: "编辑这段 Markdown",
      loading: "正在读取版本……",
      historyChanged: "目录中的当前版本已变化；请关闭编辑器并重新打开后再保存。",
      unknownCitation: "引用不在当前参考文献中：",
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
      readerLineHeight: "行距",
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
      colors: "Color for this role and priority",
      foreground: "Foreground",
      background: "Background",
      roleDefaultColors: "Use role default",
      resizeContents: "Resize contents",
      advanced: "Preview and more settings",
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
      references: "References",
      originalTerm: "Original term",
      translatedTerm: "Translation",
      definition: "Definition",
      view: "View",
      showLayers: "Show content",
      original: "Original",
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
      markdownScope: "Markdown content",
      allLatest: "All latest",
      changedLatest: "Latest changes only",
      noExportChanges: "No changed content to export",
      fullHtml: "Full text => Single HTML",
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
      saveBeforeExit: "Save the changes before leaving this editor, or leave without saving.",
      discardChanges: "Don't save",
      saveChanges: "Save changes",
      continueEditing: "Continue editing",
      saveFailedInEditor: "The save could not be completed. Changes remain in the editor; check the page status and try again.",
      editContent: "Edit this Markdown",
      loading: "Loading revisions…",
      historyChanged: "The current directory revision changed; close and reopen the editor before saving.",
      unknownCitation: "Citation is absent from the bibliography: ",
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
      readerLineHeight: "Line height",
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

  function labelToolButton(button, label) {
    button.setAttribute("aria-label", label);
    button.title = label;
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
      "--alc-reader-width", String(96 * next.width / 100) + "rem"
    );
    body.classList.toggle("alc-stacked-layout", next.layout === "stacked");
    body.dataset.alcReaderLayout = next.layout;
    body.dataset.alcReaderEditActivation = next.editActivation;
    body.dataset.alcReaderEnglishFont = next.englishFont;
    body.dataset.alcReaderChineseFont = next.chineseFont;
    body.dataset.alcReaderScale = String(next.scale);
    body.dataset.alcReaderLineHeight = String(next.lineHeight);
    body.dataset.alcReaderWidth = String(next.width);
    syncReaderPreferenceControls();
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
    var width = document.getElementById("alc-settings-width-value");
    if (scale) scale.textContent = Math.round(preferences.scale) + "%";
    if (line) line.textContent = Number(preferences.lineHeight).toFixed(2);
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
    ].forEach(installCustomSelect);

    state.readerPreferences = readerPreferenceSnapshot();
    applyReaderPreferences(state.readerPreferences);
    state.readerSettingsReady = true;

    trigger.addEventListener("click", function () {
      panel.hidden = !panel.hidden;
      trigger.setAttribute("aria-expanded", String(!panel.hidden));
      if (!panel.hidden) close.focus();
    });
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
          width: state.readerPreferences.width
        });
      });
    });
    ["scale", "line", "width"].forEach(function (name) {
      document.getElementById("alc-settings-" + name).addEventListener(
        "input", function (event) {
          var changes = {};
          if (name === "scale") changes.scale = Number(event.target.value);
          if (name === "line") changes.lineHeight = Number(event.target.value);
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
    if (listbox.parentElement !== document.body) document.body.appendChild(listbox);
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
    var field = select.closest(".alc-settings-field, .alc-speech-field");
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

  function renderMarkdown(markdown) {
    var wrapper = element("div", "alc-markdown");
    wrapper.innerHTML = state.md.render(normalizeMarkdown(markdown), {
      citationNumbers: citationNumbers(),
      citationTargets: citationTargets()
    });
    removeVisibleHtmlTags(wrapper);
    decorateGlossary(wrapper, "target");
    typeset(wrapper);
    return wrapper;
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
    var codeLines = new Set();
    state.md.parse(normalized, {}).forEach(function (token) {
      if (
        ["fence", "code_block"].indexOf(token.type) < 0 ||
        !Array.isArray(token.map)
      ) return;
      for (var index = token.map[0]; index < token.map[1]; index += 1) {
        codeLines.add(index);
      }
    });
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
      return {selected: null, diagnostics: diagnostics};
    }
    var current = uniqueRoots[0];
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
    return {selected: current, diagnostics: diagnostics};
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
    document.documentElement.lang = profile.target_language ||
      profile.source_language || "und";
    var titlePromotion = updatePrimaryTitleState(documentValue);
    var header = document.getElementById("alc-book-header");
    header.replaceChildren();
    var heading = element("h1", "", title);
    removeVisibleHtmlTags(heading);
    header.appendChild(heading);
    decorateGlossary(heading, "source");
    decorateGlossary(heading, "target");
    if (titlePromotion) {
      var translatedTitle = renderFragment(titlePromotion.fragment);
      translatedTitle.classList.add("alc-translated-title");
      translatedTitle.lang = titlePromotion.fragment.language ||
        profile.target_language || document.documentElement.lang;
      header.appendChild(translatedTitle);
    }
    if (Array.isArray(profile.authors) && profile.authors.length) {
      header.appendChild(element("p", "alc-authors", profile.authors.join(", ")));
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
        }
      }
    });
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
        var block = documentValue.blocks[index];
        if (isPdfPageMarkerBlock(block) || isStandaloneHtmlCommentBlock(block)) {
          continue;
        }
        documentNotesBefore(block.block_id).forEach(function (note) {
          content.appendChild(renderDocumentNote(note));
        });
        content.appendChild(renderSourceRow(
          block, state.fragmentGroups.get(block.block_id) || []
        ));
      }
      if (chunk.block_end === documentValue.blocks.length) {
        documentNotesBefore(null).forEach(function (note) {
          content.appendChild(renderDocumentNote(note));
        });
      }
    } else {
      renderGlossary(content, publication.glossary || [], labels());
      renderBibliography(content, publication.bibliography || [], labels());
    }
    node.replaceChildren(content);
    applyVisibility(node);
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
    if (fragmentIsVisible(selected)) values.push(selected);
    values.sort(function (left, right) {
      return left.priority - right.priority ||
        left.fragment_id.localeCompare(right.fragment_id);
    });
    state.fragmentGroups.set(target, values);
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
    if (targetId.indexOf("reference-") === 0) {
      return state.chunkByTargetId.get("alc-references") || null;
    }
    return state.chunkByTargetId.get(targetId) || null;
  }

  function hashTargetId(hash) {
    if (!hash || hash.charAt(0) !== "#") return "";
    try {
      return decodeURIComponent(hash.slice(1));
    } catch (_error) {
      return hash.slice(1);
    }
  }

  function sourceTitle(documentValue) {
    var first = (documentValue.blocks || []).find(function (block) {
      return block.kind === "heading" && block.payload &&
        Number(block.payload.level) === 1;
    });
    return first ? first.payload.text : "";
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

  function renderSourceRow(block, fragments) {
    var row = element("article", "alc-source-row");
    row.id = "block-" + safeToken(block.block_id);
    row.dataset.blockId = block.block_id;
    row.dataset.blockKind = block.kind;
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
    source.appendChild(renderSourceBlock(block));
    source.appendChild(renderCardActions("source", block.block_id, null));
    lanes.appendChild(source);

    fragments.filter(function (item) {
      return item.priority <= 100 &&
        item.fragment_id !== state.primaryTitleFragmentId;
    }).forEach(function (item) {
      var card = renderFragment(item);
      if (block.kind === "figure" && item.role === "translation") {
        mirrorSourceFigure(source, card);
      }
      lanes.appendChild(card);
    });
    row.appendChild(lanes);

    var full = fragments.filter(function (item) {
      return item.priority >= 101;
    });
    if (full.length) {
      var fullRows = element("div", "alc-full-rows");
      full.forEach(function (item) { fullRows.appendChild(renderFragment(item)); });
      row.appendChild(fullRows);
    }
    var noteButton = iconButton(
      "alc-note-button alc-icon-button", "+", labels().addNote
    );
    noteButton.addEventListener("click", function () {
      openNewEditor(block);
    });
    row.appendChild(noteButton);
    return row;
  }

  function mirrorSourceFigure(source, card) {
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
    saved.insertAdjacentElement("beforebegin", figure);
    card.classList.add("alc-translation-figure-card");
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

  function renderSourceBlock(block) {
    var payload = block.payload || {};
    var container = document.createDocumentFragment();
    if (block.kind === "heading") {
      var level = Math.max(2, Math.min(6, Number(payload.level) + 1));
      var heading = element("h" + level, "", payload.text || "");
      heading.id = "heading-" + safeToken(block.block_id);
      container.appendChild(heading);
      removeVisibleHtmlTags(heading);
      decorateGlossary(heading, "source");
      return container;
    }
    if (block.kind === "paragraph") {
      var paragraph = element("p");
      appendInlineSpans(paragraph, payload.inline_spans, payload.text);
      container.appendChild(paragraph);
      return container;
    }
    if (block.kind === "list") {
      var list = element(payload.ordered ? "ol" : "ul");
      (payload.items || []).forEach(function (item) {
        var listItem = element("li");
        appendInlineSpans(listItem, item.inline_spans, item.text);
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
      var table = element("table");
      if (payload.caption) table.appendChild(element("caption", "", payload.caption));
      if ((payload.headers || []).length) {
        var head = element("thead");
        var headerRow = element("tr");
        payload.headers.forEach(function (value) {
          headerRow.appendChild(element("th", "", value));
        });
        head.appendChild(headerRow);
        table.appendChild(head);
      }
      var body = element("tbody");
      (payload.rows || []).forEach(function (values) {
        var tr = element("tr");
        values.forEach(function (value) {
          tr.appendChild(element("td", "", value));
        });
        body.appendChild(tr);
      });
      table.appendChild(body);
      container.appendChild(table);
      removeVisibleHtmlTags(table);
      decorateGlossary(table, "source");
      return container;
    }
    if (block.kind === "figure") {
      var figure = element("figure");
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
      if (payload.caption) figure.appendChild(element("figcaption", "", payload.caption));
      container.appendChild(figure);
      removeVisibleHtmlTags(figure);
      decorateGlossary(figure, "source");
      return container;
    }
    container.appendChild(element("p", "", JSON.stringify(payload)));
    removeVisibleHtmlTags(container);
    return container;
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
    if (label) row.appendChild(element("span", "alc-equation-label", label));
    return row;
  }

  function appendInlineSpans(parent, spans, fallback) {
    if (!Array.isArray(spans) || spans.length === 0) {
      parent.textContent = fallback || "";
      removeVisibleHtmlTags(parent);
      decorateGlossary(parent, "source");
      return;
    }
    spans.forEach(function (span) {
      if (span.kind === "math") {
        var math = element("span", "math math-inline", span.source || span.tex || "");
        math.dataset.tex = span.tex || span.source || "";
        parent.appendChild(math);
      } else if (span.kind === "link") {
        var link = element("a", "", span.text || span.target || "");
        link.href = span.target || "";
        link.rel = "noopener noreferrer";
        parent.appendChild(link);
      } else {
        parent.appendChild(document.createTextNode(span.text || ""));
      }
    });
    removeVisibleHtmlTags(parent);
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
    var title = visual.title ? element("h4", "", visual.title) : element("span");
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
    var rendered = renderMarkdown(fragment.markdown_body);
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
    }
    return card;
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

  function clearPendingReaderLink() {
    if (state.pendingReaderLinkTimer !== null) {
      window.clearTimeout(state.pendingReaderLinkTimer);
      state.pendingReaderLinkTimer = null;
    }
    state.pendingReaderLinkHref = "";
  }

  function followReaderLink(href) {
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
      activateHashTarget(url.hash, true);
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
      followReaderLink(href);
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
    root.appendChild(textarea);
    window.requestAnimationFrame(function () {
      resizeInlineTextarea(textarea);
      textarea.focus();
      textarea.setSelectionRange(textarea.value.length, textarea.value.length);
    });
    return root;
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
    });
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
      loopNone: '<path d="m17 2 4 4-4 4"></path><path d="M3 11V9a3 3 0 0 1 3-3h14"></path>' +
        '<path d="m7 22-4-4 4-4"></path><path d="M21 13v2a3 3 0 0 1-3 3H4"></path>' +
        '<path d="m4 4 16 16"></path>',
      loopAll: '<path d="m17 2 4 4-4 4"></path><path d="M3 11V9a3 3 0 0 1 3-3h14"></path>' +
        '<path d="m7 22-4-4 4-4"></path><path d="M21 13v2a3 3 0 0 1-3 3H4"></path>',
      loopOne: '<path d="m17 2 4 4-4 4"></path><path d="M3 11V9a3 3 0 0 1 3-3h14"></path>' +
        '<path d="m7 22-4-4 4-4"></path><path d="M21 13v2a3 3 0 0 1-3 3H4"></path>' +
        '<path d="M11 10.5 13 9v6"></path>',
      speaker: '<path d="M4 10h4l4-3v10l-4-3H4Z"></path>' +
        '<path d="M15 9a4 4 0 0 1 0 6M17.5 6.5a7.5 7.5 0 0 1 0 11"></path>',
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
    document.getElementById("alc-speech-content-label").textContent =
      strings.readContent;
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
      if (!panel.hidden) refreshSpeechVoices();
    });
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
    var content = renderMarkdown(fragment.markdown_body);
    return normalizeSpeechText([
      fragment.title || "",
      speechTextFromNode(content)
    ].filter(Boolean).join("\n"));
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

  function speechSegmentText(segment) {
    if (segment.text !== null && segment.text !== undefined) return segment.text;
    segment.text = fragmentSpeechText(segment.fragment);
    return segment.text;
  }

  function speechSegmentNode(segment) {
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
      holder.innerHTML = state.md.render(normalizeMarkdown(candidate.markdown_body));
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
      var row = element("div", "alc-glossary-row");
      var original = element("dt", "", entry.term || entry.source_term || "");
      var translated = element(
        "dd", "", entry.translated_term || entry.translation || ""
      );
      decorateGlossary(original, "source");
      decorateGlossary(translated, "target");
      row.appendChild(original);
      row.appendChild(translated);
      row.appendChild(element("dd", "", entry.definition || ""));
      dl.appendChild(row);
    });
    section.appendChild(dl);
    main.appendChild(section);
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
      term.dataset.glossaryTooltip = tooltipText(
        match.entries.map(function (item) { return item.entry; })
      );
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
    return entries.map(function (entry) {
      return strings.originalTerm + ": " + (entry.term || entry.source_term || "") +
        "\n" + strings.translatedTerm + ": " +
        (entry.translated_term || entry.translation || "") +
        "\n" + strings.definition + ": " + (entry.definition || "");
    }).join("\n\n");
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
    var repairedMathShifts = katexTex(repairOldStyleMathShifts(value));
    var repairedTextBoxes = katexTex(
      repairTextBoxes(repairOldStyleMathShifts(value))
    );
    // Repair a stripped array before generic bare-ampersand handling wraps it
    // as an aligned equation.
    var repairedArrays = katexTex(
      repairArrayEnvironment(
        repairTextBoxes(repairOldStyleMathShifts(value))
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
          strict: "warn"
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
      activateHashTarget(href, true);
    });
    window.addEventListener("hashchange", function () {
      activateHashTarget(window.location.hash, false);
    });
    window.addEventListener("popstate", function () {
      activateHashTarget(window.location.hash, false);
    });
    state.navigationReady = true;
  }

  function activateHashTarget(hash, updateHistory) {
    var targetId = hashTargetId(hash);
    if (targetId === "alc-book-header") {
      if (updateHistory) {
        if (window.location.hash === hash) {
          window.history.replaceState(null, "", hash);
        } else {
          window.history.pushState(null, "", hash);
        }
      }
      state.hashCalibration = null;
      scrollToReaderTop();
      return true;
    }
    var chunk = chunkForTargetId(targetId);
    if (!chunk) return false;
    renderChunk(chunk);
    armHashCalibration(hash);
    if (updateHistory) {
      if (window.location.hash === hash) {
        window.history.replaceState(null, "", hash);
      } else {
        window.history.pushState(null, "", hash);
      }
    }
    scrollToHashTarget(targetId);
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

  function armHashCalibration(hash) {
    var targetId = hashTargetId(hash);
    if (!targetId || !chunkForTargetId(targetId)) return;
    state.hashCalibration = {targetId: targetId};
    recalibrateHashTarget();
  }

  function recalibrateHashTarget() {
    var calibration = state.hashCalibration;
    if (!calibration) return;
    scrollToHashTarget(calibration.targetId);
  }

  function scrollToHashTarget(targetId) {
    window.requestAnimationFrame(function () {
      var target = document.getElementById(targetId);
      if (!target) return;
      var root = document.documentElement;
      var previousBehavior = root.style.scrollBehavior;
      root.style.scrollBehavior = "auto";
      target.scrollIntoView({block: "start", behavior: "auto"});
      root.style.scrollBehavior = previousBehavior;
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
      tooltip.textContent = "";
      active = null;
    }
    function open(term) {
      var content = term && term.dataset.glossaryTooltip;
      if (!content) return;
      active = term;
      tooltip.textContent = content;
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
    document.getElementById("alc-export-scope-label").textContent =
      strings.markdownScope;
    document.getElementById("alc-export-all-label").textContent =
      strings.allLatest;
    document.getElementById("alc-export-changed-label").textContent =
      strings.changedLatest;
    document.getElementById("alc-export-empty").textContent =
      strings.noExportChanges;
    var htmlButton = document.getElementById("alc-export-html");
    htmlButton.textContent = strings.fullHtml;
    htmlButton.title = state.exportStandaloneSupported ? "" :
      strings.exportUnavailable;
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
    htmlButton.addEventListener("click", function () {
      runExport({kind: "html"});
    });
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
    var empty = document.getElementById("alc-export-empty");
    root.replaceChildren();
    var roles = Array.from(new Set(selectedForMarkdown(exportScope()).map(
      function (revision) { return revision.role; }
    )));
    var preferred = ["translation", "companion", "guide", "note"];
    roles.sort(function (left, right) {
      var leftIndex = preferred.indexOf(left);
      var rightIndex = preferred.indexOf(right);
      if (leftIndex < 0) leftIndex = preferred.length;
      if (rightIndex < 0) rightIndex = preferred.length;
      return leftIndex - rightIndex || left.localeCompare(right);
    });
    roles.forEach(function (role) {
      var button = element("button", "", roleLabel(role) + " => MD");
      button.type = "button";
      button.disabled = state.exportInProgress;
      button.addEventListener("click", function () {
        runExport({kind: "markdown", role: role});
      });
      root.appendChild(button);
    });
    empty.hidden = roles.length > 0 || exportScope() !== "changed";
    var scopeControls = document.querySelectorAll(
      'input[name="alc-export-scope"]'
    );
    Array.prototype.forEach.call(scopeControls, function (input) {
      input.disabled = state.exportInProgress;
    });
    var htmlButton = document.getElementById("alc-export-html");
    var changedOnly = exportScope() === "changed";
    htmlButton.hidden = changedOnly;
    htmlButton.disabled = changedOnly || state.exportInProgress ||
      !state.exportStandaloneSupported;
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
      loadAllPayload(request.kind === "html");
      if (state.directory) {
        setStatus(labels().exportLoading);
        if (!await loadDirectoryRevisions(state.directory)) {
          throw new Error(labels().exportSyncFailed);
        }
      }
      if (request.kind === "markdown") {
        var markdown = buildRoleMarkdown(request.role, exportScope());
        if (!markdown) {
          setStatus(labels().noExportChanges);
          return;
        }
        downloadText(
          exportFilename(request.role, "md"),
          markdown,
          "text/markdown;charset=utf-8"
        );
      } else {
        if (!state.exportStandaloneSupported) {
          throw new Error(labels().exportUnavailable);
        }
        downloadText(
          exportFilename("latest", "html"),
          buildStandaloneExportHtml(),
          "text/html;charset=utf-8"
        );
      }
      closeExportPanel(false);
      setStatus(labels().exportStarted);
    } catch (error) {
      setStatus(String(error.message || error), "error");
    } finally {
      state.exportInProgress = false;
      renderExportOptions();
    }
  }

  function buildRoleMarkdown(role, scope) {
    var revisions = selectedForMarkdown(scope).filter(function (revision) {
      return revision.role === role;
    });
    if (!revisions.length) return "";
    var blockOrder = new Map(
      (state.payload.publication.source_document.blocks || []).map(
        function (block, index) { return [block.block_id, index]; }
      )
    );
    revisions.sort(function (left, right) {
      var leftTarget = fragmentTargetId(left);
      var rightTarget = fragmentTargetId(right);
      var leftOrder = blockOrder.has(leftTarget) ? blockOrder.get(leftTarget) : Infinity;
      var rightOrder = blockOrder.has(rightTarget) ? blockOrder.get(rightTarget) : Infinity;
      return leftOrder - rightOrder || left.priority - right.priority ||
        left.fragment_id.localeCompare(right.fragment_id);
    });
    var parts = ["# " + markdownHeading(readerTitle() + " — " + roleLabel(role))];
    revisions.forEach(function (revision) {
      if (revision.title) parts.push("## " + markdownHeading(revision.title));
      parts.push(normalizeMarkdown(revision.markdown_body).replace(/\n+$/, ""));
    });
    return parts.filter(function (part) { return part !== ""; }).join("\n\n") + "\n";
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
    var url = URL.createObjectURL(new Blob([value], {type: mediaType}));
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
    var revisionState = exportRevisionState();
    payload.revisions = revisionState.revisions;
    payload.selected_revision_digests = revisionState.selected_revision_digests;
    var encoded = JSON.stringify(payload).replace(/<\/script/gi, "<\\/script");
    var pattern = /(<script[^>]*\bid=["']alc-render-payload["'][^>]*>)[\s\S]*?(<\/script>)/i;
    if (!pattern.test(state.exportHtmlTemplate)) {
      throw new Error(labels().exportUnavailable);
    }
    return state.exportHtmlTemplate.replace(
      /<script[^>]*class=["']alc-render-reader-(?:chunk|resource)["'][^>]*>[\s\S]*?<\/script>/gi,
      ""
    ).replace(pattern, function (_match, open, close) {
      return open + encoded + close;
    });
  }

  function activeInlineDraftCard() {
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
        if (!state.activeDraft) {
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
    document.getElementById("alc-editor-markdown-label").textContent =
      strings.markdown;
    document.getElementById("alc-editor-preview-label").textContent =
      strings.preview;
    document.getElementById("alc-editor-advanced-label").textContent =
      strings.advanced;
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
    Array.prototype.forEach.call(
      document.getElementById("alc-editor-role").options,
      function (option) { option.textContent = strings[option.value] || option.value; }
    );
    close.onclick = closeEditorDialog;
    document.getElementById("alc-editor-cancel").onclick = closeEditorDialog;
    dialog.addEventListener("cancel", function (event) {
      event.preventDefault();
      if (!state.saveInProgress) closeEditorDialog();
    });
    document.getElementById("alc-editor-title").addEventListener(
      "input", syncDraftAndSaveState
    );
    document.getElementById("alc-editor-role").addEventListener("change", function () {
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
    if (state.activeDraft && !state.saveInProgress) {
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
        return commitDirectorySnapshot(
          handle, revisions, revisionDigests, fileDiagnostics, nextCache, generation
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
    return commitDirectorySnapshot(
      handle, revisions, revisionDigests, fileDiagnostics, nextCache, generation
    );
  }

  function commitDirectorySnapshot(
    handle, revisions, revisionDigests, fileDiagnostics, fileCache, generation
  ) {
    if (generation !== state.directoryLoadGeneration) return false;
    var previousSelected = new Map(state.selected);
    state.directory = handle;
    state.revisions = revisions;
    state.revisionDigests = revisionDigests;
    state.fileDiagnostics = fileDiagnostics;
    state.directoryCacheHandle = handle;
    state.directoryFileCache = fileCache;
    resolveAll();
    refreshChangedSelections(previousSelected);
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

  function openEditEditor(fragment) {
    beginInlineEdit(fragment);
  }

  function beginInlineEdit(fragment) {
    if (state.exportInProgress || state.directorySelectionInProgress) {
      setStatus(labels().revisionBusy, "error");
      return;
    }
    if (state.saveInProgress) return;
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

  function focusActiveDraft() {
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
    if (!state.activeDraft) return true;
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
    if (!state.activeDraft || state.saveInProgress) return;
    var dialog = document.getElementById("alc-editor-dialog");
    var draft = state.activeDraft;
    state.editorGeneration += 1;
    document.getElementById("alc-editor-heading").textContent =
      heading || labels().editor;
    document.getElementById("alc-editor-title").value = draft.title || "";
    document.getElementById("alc-editor-role").value = draft.role || "note";
    document.getElementById("alc-editor-priority").value = String(draft.priority || 110);
    document.getElementById("alc-editor-markdown").value = draft.markdown_body || "";
    syncAppearanceControlsFromDraft();
    state.editorPreviewDirty = true;
    var deleteButton = document.getElementById("alc-editor-delete");
    if (deleteButton) {
      deleteButton.hidden = !draft.base || draft.base.deleted === true;
    }
    renderHistory(draft.base && draft.base.fragment_id);
    updatePreview();
    updateDraftSaveButtons();
    dialog.showModal();
  }

  function closeEditorDialog() {
    if (state.saveInProgress) return;
    var dialog = document.getElementById("alc-editor-dialog");
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

  function replaceFragmentCard(fragmentId, anchor) {
    var current = state.selected.get(fragmentId);
    var card = document.querySelector(
      '.alc-fragment[data-fragment-id="' + cssString(fragmentId) + '"]'
    );
    if (!fragmentIsVisible(current) && card && typeof card.remove === "function") {
      card.remove();
    } else if (current && card && typeof card.replaceWith === "function") {
      card.replaceWith(renderFragment(current));
    }
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
      var button = element("button", "", "v" + revision.revision);
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

  function historyPane(title, markdown) {
    var pane = element("section", "alc-history-pane");
    pane.appendChild(element("h3", "", title));
    pane.appendChild(element("pre", "", markdown || ""));
    return pane;
  }

  function restoreHistoricalRevision() {
    var revision = state.editorHistorical;
    if (!revision || !state.activeDraft) return;
    state.activeDraft.title = revision.title || null;
    state.activeDraft.role = revision.role;
    state.activeDraft.priority = revision.priority;
    state.activeDraft.markdown_body = revision.markdown_body;
    state.activeDraft.appearance = appearanceForGroup(
      revision.role, revision.priority
    );
    document.getElementById("alc-editor-title").value = revision.title || "";
    document.getElementById("alc-editor-role").value = revision.role;
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
    if (!state.activeDraft) return;
    var dialog = document.getElementById("alc-editor-dialog");
    if (!dialog || !dialog.open) return;
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
    return persistEditor(event, false);
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
    status.textContent = value || "";
    status.dataset.kind = kind || "info";
    status.hidden = !value;
    if (!value) return;
    var timer = window.setTimeout(function () {
      if (state.statusTimer !== timer) return;
      state.statusTimer = null;
      status.textContent = "";
      status.hidden = true;
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
      initialRevisions();
      captureInitialSelection();
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
