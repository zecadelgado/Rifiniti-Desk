import 'dart:async';
import 'dart:io';

import 'package:emoji_picker_flutter/emoji_picker_flutter.dart';
import 'package:file_picker/file_picker.dart';
import 'package:flutter/material.dart';
import 'package:flutter/foundation.dart' as foundation;
import 'package:flutter/services.dart';
import 'package:flutter_contacts/flutter_contacts.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:geolocator/geolocator.dart';
import 'package:go_router/go_router.dart';
import 'package:image_picker/image_picker.dart';
import 'package:just_audio/just_audio.dart';
import 'package:open_filex/open_filex.dart';
import 'package:path_provider/path_provider.dart';
import 'package:permission_handler/permission_handler.dart';
import 'package:record/record.dart';
import 'package:url_launcher/url_launcher.dart';
import 'package:video_player/video_player.dart';

import '../../../../core/routing/app_routes.dart';
import '../../../../core/theme/app_colors.dart';
import '../../../../core/utils/date_time_utils.dart';
import '../../../../data/models/attachment.dart';
import '../../../../data/models/chat_message_item.dart';
import '../../../../data/models/conversation.dart';
import '../../../../data/models/message.dart';
import '../../../../data/models/message_reaction_entry.dart';
import '../../../../shared/types/enums.dart';
import '../../../../shared/widgets/lero_avatar.dart';
import '../../../../shared/widgets/lero_empty_state.dart';
import '../../../../shared/widgets/lero_error_banner.dart';
import '../../../../shared/widgets/lero_skeleton.dart';
import '../../../../state/app_providers.dart';
import '../../../../state/auth_providers.dart';
import '../../../../state/chat_providers.dart';
import '../../../../state/inbox_providers.dart';
import '../../../../state/internal_chat_providers.dart';
import 'chat_favorites_page.dart';
import 'chat_media_links_docs_page.dart';
import 'chat_notes_page.dart';
import 'chat_search_page.dart';
import '../widgets/chat_composer.dart';

class ChatPage extends ConsumerStatefulWidget {
  const ChatPage({super.key, required this.conversationId});

  final String conversationId;

  @override
  ConsumerState<ChatPage> createState() => _ChatPageState();
}

class _ChatPageState extends ConsumerState<ChatPage> {
  static const double _scrollToBottomButtonThreshold = 80;
  static const double _nearBottomThreshold = 100;
  static const List<String> _quickReactionEmojis = <String>[
    '👍',
    '❤️',
    '😂',
    '😮',
    '😢',
    '🙏',
    '🎉',
  ];
  static const List<String> _documentExtensions = [
    'pdf',
    'doc',
    'docx',
    'xls',
    'xlsx',
    'ppt',
    'pptx',
    'txt',
    'csv',
    'zip',
    'rar',
  ];

  final TextEditingController _messageController = TextEditingController();
  final FocusNode _messageFocusNode = FocusNode();
  final ScrollController _messagesScrollController = ScrollController();
  final ImagePicker _imagePicker = ImagePicker();
  final AudioRecorder _audioRecorder = AudioRecorder();
  final AudioPlayer _audioDraftPlayer = AudioPlayer();
  final Map<String, GlobalKey> _messageItemKeys = <String, GlobalKey>{};
  StreamSubscription<Duration?>? _audioDraftDurationSub;
  StreamSubscription<Duration>? _audioDraftPositionSub;
  StreamSubscription<PlayerState>? _audioDraftStateSub;
  Timer? _audioRecordingTicker;
  Timer? _favoriteHighlightTimer;
  // Timer? _internalConversationRefreshTimer;
  bool _showDownloadBar = false;
  bool _showScrollToBottom = false;
  bool _isQuickActionsMenuOpen = false;
  bool _isEmojiPickerVisible = false;
  bool _isAudioRecording = false;
  bool _isAudioRecordingPaused = false;
  bool _isAudioDraftPreparing = false;
  bool _hasAudioDraftLoadError = false;
  bool _isAudioDraftPlaying = false;
  Duration _audioRecordingDuration = Duration.zero;
  Duration _audioDraftDuration = Duration.zero;
  Duration _audioDraftPosition = Duration.zero;
  String? _audioDraftPath;
  double _audioDraftSpeed = 1.0;
  final String _selectedTime = '16:34';
  String? _highlightedMessageId;
  Message? _replyingToMessage;
  Set<String> _selectedMessageIds = <String>{};
  bool _didInitialScroll = false;
  int _lastMessageCount = 0;
  bool _forceScrollToBottomOnNextMessage = false;
  ProviderSubscription<AsyncValue<Conversation?>>? _conversationEffectSub;
  ProviderSubscription<AsyncValue<List<ChatMessageItem>>>?
  _messageItemsEffectSub;
  bool _didTriggerMarkAsRead = false;
  String _lastSyncedMessageSignature = '';

  bool get _hasPendingAudioDraft => _audioDraftPath != null;

  @override
  void initState() {
    super.initState();
    _messagesScrollController.addListener(_handleMessagesScroll);
    _messageFocusNode.addListener(_handleComposerFocusChange);
    _registerProviderEffects();
    _audioDraftDurationSub = _audioDraftPlayer.durationStream.listen((
      duration,
    ) {
      if (!mounted || duration == null) return;
      setState(() {
        _audioDraftDuration = duration;
      });
    });
    _audioDraftPositionSub = _audioDraftPlayer.positionStream.listen((
      position,
    ) {
      if (!mounted) return;
      setState(() {
        _audioDraftPosition = position;
      });
    });
    _audioDraftStateSub = _audioDraftPlayer.playerStateStream.listen((state) {
      if (!mounted) return;
      setState(() {
        _isAudioDraftPlaying = state.playing;
      });
      if (state.processingState == ProcessingState.completed) {
        unawaited(_audioDraftPlayer.seek(Duration.zero));
      }
    });
  }

  @override
  void dispose() {
    _audioRecordingTicker?.cancel();
    _favoriteHighlightTimer?.cancel();
    _conversationEffectSub?.close();
    _messageItemsEffectSub?.close();
    unawaited(_audioDraftDurationSub?.cancel());
    unawaited(_audioDraftPositionSub?.cancel());
    unawaited(_audioDraftStateSub?.cancel());
    unawaited(_audioDraftPlayer.dispose());
    unawaited(_audioRecorder.dispose());
    final pendingDraftPath = _audioDraftPath;
    if (pendingDraftPath != null) {
      final file = File(pendingDraftPath);
      if (file.existsSync()) {
        unawaited(file.delete());
      }
    }
    _messagesScrollController
      ..removeListener(_handleMessagesScroll)
      ..dispose();
    _messageFocusNode
      ..removeListener(_handleComposerFocusChange)
      ..dispose();
    _messageController.dispose();
    super.dispose();
  }

  void _registerProviderEffects() {
    _conversationEffectSub = ref.listenManual<AsyncValue<Conversation?>>(
      conversationByIdProvider(widget.conversationId),
      (previous, next) {
        final conversation = next.valueOrNull;
        if (conversation == null) {
          _didTriggerMarkAsRead = false;
          return;
        }
        if (conversation.unreadCount <= 0) {
          _didTriggerMarkAsRead = false;
          return;
        }
        if (!conversation.capabilities.canMarkAsRead || _didTriggerMarkAsRead) {
          return;
        }
        _didTriggerMarkAsRead = true;
        unawaited(
          ref.read(chatActionsProvider).markConversationAsRead(
            widget.conversationId,
          ),
        );
      },
      fireImmediately: true,
    );

    _messageItemsEffectSub =
        ref.listenManual<AsyncValue<List<ChatMessageItem>>>(
          chatMessageItemsProvider(widget.conversationId),
          (previous, next) {
            final items = next.valueOrNull;
            if (items == null || !_isSelectionMode) {
              return;
            }
            final hasSelection = items.any(
              (item) => _selectedMessageIds.contains(item.message.id),
            );
            if (!hasSelection && mounted) {
              _clearSelection();
            }
          },
          fireImmediately: true,
        );
  }

  void _handleComposerFocusChange() {
    if (_messageFocusNode.hasFocus && _isAudioRecording) {
      unawaited(_cancelAudioRecording());
    }
    if (_messageFocusNode.hasFocus && _isEmojiPickerVisible) {
      setState(() {
        _isEmojiPickerVisible = false;
      });
    }
  }

  /* Future<void> _configureInternalConversationRefresh() async {
    final conversation = await ref.read(
      conversationByIdProvider(widget.conversationId).future,
    );
    if (!mounted ||
        conversation == null ||
        !_isInternalConversation(conversation)) {
      return;
    }

    _internalConversationRefreshTimer?.cancel();
    _internalConversationRefreshTimer = Timer.periodic(
      ref.read(internalChatRefreshIntervalProvider),
      (_) => unawaited(_refreshInternalConversation()),
    );
  }

  Future<void> _refreshInternalConversation() async {
    if (_isRefreshingInternalConversation) {
      return;
    }

    _isRefreshingInternalConversation = true;
    try {
      ref.invalidate(conversationByIdProvider(widget.conversationId));
      final _ = await ref.refresh(
        messageListProvider(widget.conversationId).future,
      );
    } catch (_) {
      // Async providers still expose the error state to the UI.
    } finally {
      _isRefreshingInternalConversation = false;
    }
  } */

  bool _isInternalConversation(Conversation conversation) {
    return conversation.channel == ConversationChannel.internalCollaborator ||
        conversation.channel == ConversationChannel.internalTeam;
  }

  void _handleMessagesScroll() {
    if (!_messagesScrollController.hasClients) return;
    final remaining =
        _messagesScrollController.position.maxScrollExtent -
        _messagesScrollController.offset;
    final shouldShow = remaining > _scrollToBottomButtonThreshold;
    if (shouldShow != _showScrollToBottom) {
      setState(() {
        _showScrollToBottom = shouldShow;
      });
    }
  }

  void _scrollToBottom({required bool animated}) {
    if (!_messagesScrollController.hasClients) return;
    final target = _messagesScrollController.position.maxScrollExtent;
    if (animated) {
      _messagesScrollController.animateTo(
        target,
        duration: const Duration(milliseconds: 280),
        curve: Curves.easeOut,
      );
      return;
    }
    _messagesScrollController.jumpTo(target);
  }

  void _syncScrollAfterBuild(int messageCount) {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted || !_messagesScrollController.hasClients) return;

      final remaining =
          _messagesScrollController.position.maxScrollExtent -
          _messagesScrollController.offset;
      final nearBottom = remaining < _nearBottomThreshold;
      final hasNewMessage = messageCount > _lastMessageCount;
      final shouldForceScroll = _forceScrollToBottomOnNextMessage;
      if (!_didInitialScroll ||
          shouldForceScroll ||
          (hasNewMessage && nearBottom)) {
        _scrollToBottom(animated: _didInitialScroll || shouldForceScroll);
      }
      if (shouldForceScroll && hasNewMessage) {
        _forceScrollToBottomOnNextMessage = false;
      }
      _didInitialScroll = true;
      _lastMessageCount = messageCount;
      _handleMessagesScroll();
    });
  }

  void _syncMessagesAfterBuild(List<ChatMessageItem> items) {
    final messages = items.map((item) => item.message).toList(growable: false);
    final signature = messages.map((message) => message.id).join('|');
    if (signature == _lastSyncedMessageSignature) {
      return;
    }
    _lastSyncedMessageSignature = signature;
    _syncMessageItemKeys(messages);
    _syncScrollAfterBuild(items.length);
  }

  void _requestScrollToBottomAfterSending() {
    _forceScrollToBottomOnNextMessage = true;
    _scrollToBottom(animated: true);
  }

  void _focusFavoriteMessage(String messageId) {
    _favoriteHighlightTimer?.cancel();
    setState(() {
      _highlightedMessageId = messageId;
    });
    _favoriteHighlightTimer = Timer(const Duration(seconds: 4), () {
      if (!mounted) return;
      setState(() {
        _highlightedMessageId = null;
      });
    });
    _scrollToMessage(messageId);
  }

  void _scrollToMessage(String messageId) {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      final key = _messageItemKeys[messageId];
      final itemContext = key?.currentContext;
      if (itemContext == null) return;
      Scrollable.ensureVisible(
        itemContext,
        duration: const Duration(milliseconds: 280),
        curve: Curves.easeOut,
        alignment: 0.24,
      );
    });
  }

  void _syncMessageItemKeys(List<Message> messages) {
    final validIds = messages.map((message) => message.id).toSet();
    _messageItemKeys.removeWhere((id, _) => !validIds.contains(id));
  }

  GlobalKey _messageKeyFor(String messageId) {
    return _messageItemKeys.putIfAbsent(
      messageId,
      () => GlobalKey(debugLabel: 'message_$messageId'),
    );
  }

  bool get _isSelectionMode => _selectedMessageIds.isNotEmpty;

  bool _canSelectMessage(ChatMessageItem item) {
    return item.message.senderType != MessageSenderType.system &&
        !item.isDeleted;
  }

  void _clearSelection() {
    if (!_isSelectionMode) return;
    setState(() {
      _selectedMessageIds = <String>{};
    });
  }

  void _handleMessageLongPress(ChatMessageItem item) {
    if (!_canSelectMessage(item)) return;
    setState(() {
      _selectedMessageIds = <String>{item.message.id};
    });
  }

  void _handleMessageTap(ChatMessageItem item) {
    if (!_isSelectionMode || !_canSelectMessage(item)) {
      return;
    }

    setState(() {
      final next = <String>{..._selectedMessageIds};
      if (!next.add(item.message.id)) {
        next.remove(item.message.id);
      }
      _selectedMessageIds = next;
    });
  }

  String _messageBodyText(Message message) {
    final replyPayload = _ReplyPayload.tryParse(message.text);
    return replyPayload?.body ?? message.text;
  }

  Future<void> _replyToMessage(Message message) async {
    setState(() {
      _replyingToMessage = message;
      _selectedMessageIds = <String>{};
    });
    _messageFocusNode.requestFocus();
  }

  Future<void> _toggleFavoriteSelection(
    List<ChatMessageItem> selectedItems,
  ) async {
    final eligibleIds = selectedItems
        .where((item) => item.canFavorite)
        .map((item) => item.message.id)
        .toList(growable: false);
    if (eligibleIds.isEmpty) return;

    final singleItem = selectedItems.length == 1 ? selectedItems.first : null;
    ref.read(favoriteMessageIdsProvider.notifier).toggleFavorites(eligibleIds);
    _clearSelection();
    _showFeedback(
      singleItem == null
          ? 'Favoritos atualizados.'
          : (singleItem.isFavorite
                ? 'Mensagem removida dos favoritos.'
                : 'Mensagem adicionada aos favoritos.'),
    );
  }

  Future<void> _copySelection(List<ChatMessageItem> selectedItems) async {
    final text = selectedItems
        .map((item) => _messageBodyText(item.message).trim())
        .where((value) => value.isNotEmpty)
        .join('\n\n');
    if (text.trim().isEmpty) return;

    await Clipboard.setData(ClipboardData(text: text));
    _clearSelection();
    _showFeedback(
      selectedItems.length == 1
          ? 'Mensagem copiada.'
          : '${selectedItems.length} mensagens copiadas.',
    );
  }

  Future<bool> _confirmDeleteMessages(int count) async {
    final result = await showDialog<bool>(
      context: context,
      builder: (dialogContext) {
        return AlertDialog(
          title: const Text('Excluir mensagem'),
          content: Text(
            count == 1
                ? 'Deseja apagar esta mensagem para voce?'
                : 'Deseja apagar $count mensagens para voce?',
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.of(dialogContext).pop(false),
              child: const Text('Cancelar'),
            ),
            FilledButton(
              onPressed: () => Navigator.of(dialogContext).pop(true),
              style: FilledButton.styleFrom(
                backgroundColor: AppColors.primary,
                foregroundColor: Colors.white,
              ),
              child: const Text('Excluir'),
            ),
          ],
        );
      },
    );
    return result ?? false;
  }

  Future<void> _deleteSelection(
    List<ChatMessageItem> allItems,
    List<ChatMessageItem> selectedItems,
  ) async {
    final eligibleIds = selectedItems
        .where((item) => !item.isDeleted)
        .map((item) => item.message.id)
        .toList(growable: false);
    if (eligibleIds.isEmpty) return;

    final latestVisibleItem = _latestVisibleTimelineItem(allItems);
    final shouldUpdateDeletedPreview =
        latestVisibleItem != null &&
        eligibleIds.contains(latestVisibleItem.message.id);

    final confirmed = await _confirmDeleteMessages(eligibleIds.length);
    if (!confirmed) return;

    await ref
        .read(messageInteractionsProvider(widget.conversationId).notifier)
        .markDeleted(eligibleIds);
    final conversation = await ref.read(
      conversationByIdProvider(widget.conversationId).future,
    );
    if (conversation != null &&
        _isInternalConversation(conversation) &&
        shouldUpdateDeletedPreview) {
      ref
          .read(internalConversationPreviewOverridesProvider.notifier)
          .showDeletedPreview(
            conversationId: widget.conversationId,
            isCurrentUserMessage:
                latestVisibleItem.message.senderType == MessageSenderType.agent,
            occurredAt: DateTime.now(),
            senderType: latestVisibleItem.message.senderType,
          );
    }
    _clearSelection();
    _showFeedback(
      eligibleIds.length == 1
          ? 'Mensagem apagada.'
          : '${eligibleIds.length} mensagens apagadas.',
    );
  }

  Future<void> _applyReaction(
    ChatMessageItem item,
    String emoji, {
    required String userId,
    required String userName,
  }) async {
    MessageReactionEntry? currentReaction;
    for (final reaction in item.reactions) {
      if (reaction.userId == userId) {
        currentReaction = reaction;
        break;
      }
    }
    final shouldRemove =
        currentReaction != null && currentReaction.emoji == emoji;

    final nextReaction = shouldRemove
        ? null
        : MessageReactionEntry(
            userId: userId,
            userName: userName,
            emoji: emoji,
            reactedAt: DateTime.now(),
          );

    final conversation = await ref.read(
      conversationByIdProvider(widget.conversationId).future,
    );
    if (conversation != null && _isInternalConversation(conversation)) {
      await ref
          .read(internalChatRepositoryProvider)
          .setMessageReaction(
            conversationId: widget.conversationId,
            messageId: item.message.id,
            reaction: nextReaction,
          );
      final previewOverrides = ref.read(
        internalConversationPreviewOverridesProvider.notifier,
      );
      if (nextReaction == null) {
        previewOverrides.clear(widget.conversationId);
      } else {
        previewOverrides.showReactionPreview(
          conversationId: widget.conversationId,
          actorName: nextReaction.userName,
          emoji: nextReaction.emoji,
          occurredAt: nextReaction.reactedAt,
          senderType: MessageSenderType.agent,
        );
      }

      _clearSelection();
      return;
    }

    await ref
        .read(messageInteractionsProvider(widget.conversationId).notifier)
        .setReaction(messageId: item.message.id, reaction: nextReaction);
    _clearSelection();
  }

  ChatMessageItem? _latestVisibleTimelineItem(List<ChatMessageItem> items) {
    for (final item in items.reversed) {
      if (item.message.senderType == MessageSenderType.system ||
          item.isDeleted) {
        continue;
      }
      return item;
    }
    return null;
  }

  Future<void> _openReactionPicker(
    ChatMessageItem item, {
    required String userId,
    required String userName,
  }) async {
    final reactionSearchController = TextEditingController();
    final selectedEmoji = await showModalBottomSheet<String>(
      context: context,
      showDragHandle: true,
      backgroundColor: Colors.white,
      builder: (sheetContext) {
        return SafeArea(
          child: SizedBox(
            height: 360,
            child: EmojiPicker(
              onEmojiSelected: (_, emoji) {
                Navigator.of(sheetContext).pop(emoji.emoji);
              },
              textEditingController: reactionSearchController,
              onBackspacePressed: () {},
              config: const Config(
                height: 320,
                checkPlatformCompatibility: true,
                emojiViewConfig: EmojiViewConfig(columns: 8, emojiSizeMax: 28),
                skinToneConfig: SkinToneConfig(enabled: true),
                categoryViewConfig: CategoryViewConfig(
                  indicatorColor: AppColors.primary,
                ),
                bottomActionBarConfig: BottomActionBarConfig(enabled: false),
                searchViewConfig: SearchViewConfig(),
              ),
            ),
          ),
        );
      },
    );
    reactionSearchController.dispose();

    if (!mounted || selectedEmoji == null || selectedEmoji.trim().isEmpty) {
      return;
    }
    await _applyReaction(
      item,
      selectedEmoji,
      userId: userId,
      userName: userName,
    );
  }

  Future<void> _forwardMessages(List<Message> sourceMessages) async {
    List<Conversation> conversations;
    try {
      conversations = await ref
          .read(conversationsRepositoryProvider)
          .listConversations(channels: const {ConversationChannel.whatsapp});
    } catch (_) {
      if (!mounted) return;
      _showFeedback('Nao foi possivel carregar a lista de chats.');
      return;
    }

    if (!mounted) return;
    if (conversations.isEmpty) {
      _showFeedback('Nenhum chat disponivel para encaminhar.');
      return;
    }

    final target = await showModalBottomSheet<Conversation>(
      context: context,
      showDragHandle: true,
      backgroundColor: const Color(0xFFF8F9FB),
      builder: (sheetContext) {
        return SafeArea(
          child: Padding(
            padding: const EdgeInsets.fromLTRB(14, 6, 14, 14),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Text(
                  'Encaminhar para',
                  style: TextStyle(
                    color: Color(0xFF111827),
                    fontSize: 18,
                    fontWeight: FontWeight.w700,
                  ),
                ),
                const SizedBox(height: 8),
                SizedBox(
                  height: (conversations.length * 64.0)
                      .clamp(
                        80.0,
                        MediaQuery.of(sheetContext).size.height * 0.55,
                      )
                      .toDouble(),
                  child: ListView.builder(
                    itemCount: conversations.length,
                    itemBuilder: (context, index) {
                      final conversation = conversations[index];
                      return ListTile(
                        contentPadding: EdgeInsets.zero,
                        leading: LeroAvatar(
                          text: conversation.contactAvatarUrl,
                          size: 36,
                        ),
                        title: Text(conversation.contactName),
                        subtitle: Text(
                          conversation.id == widget.conversationId
                              ? 'Chat atual'
                              : 'WhatsApp',
                        ),
                        onTap: () =>
                            Navigator.of(sheetContext).pop(conversation),
                      );
                    },
                  ),
                ),
              ],
            ),
          ),
        );
      },
    );

    if (!mounted || target == null) return;

    try {
      for (final sourceMessage in sourceMessages) {
        final forwardedText = sourceMessage.text.trim();
        final forwardedAttachments = _cloneAttachments(
          sourceMessage.attachments,
        );
        if (forwardedText.isEmpty && forwardedAttachments.isEmpty) {
          continue;
        }
        await ref
            .read(chatActionsProvider)
            .sendMessage(
              conversationId: target.id,
              text: forwardedText,
              attachments: forwardedAttachments,
            );
      }
      if (!mounted) return;
      if (target.id == widget.conversationId) {
        _requestScrollToBottomAfterSending();
      }
      _clearSelection();
      _showFeedback(
        sourceMessages.length == 1
            ? (target.id == widget.conversationId
                  ? 'Mensagem encaminhada.'
                  : 'Mensagem encaminhada para ${target.contactName}.')
            : (target.id == widget.conversationId
                  ? '${sourceMessages.length} mensagens encaminhadas.'
                  : '${sourceMessages.length} mensagens encaminhadas para ${target.contactName}.'),
      );
    } catch (_) {
      if (!mounted) return;
      _showFeedback('Falha ao encaminhar as mensagens.');
    }
  }

  List<Attachment> _cloneAttachments(List<Attachment> attachments) {
    return attachments
        .map(
          (attachment) => Attachment(
            id: 'att_fwd_${DateTime.now().microsecondsSinceEpoch}_${attachment.id}',
            fileName: attachment.fileName,
            type: attachment.type,
            sizeKb: attachment.sizeKb,
            url: attachment.url,
          ),
        )
        .toList(growable: false);
  }

  String _messagePreviewText(Message message) {
    final text = _messageBodyText(message).trim();
    if (text.isNotEmpty) return _truncateText(text, maxChars: 80);
    if (message.attachments.isEmpty) return 'Mensagem';

    final attachment = message.attachments.first;
    switch (attachment.type) {
      case AttachmentType.audio:
        return '[Audio]';
      case AttachmentType.video:
        return '[Video]';
      case AttachmentType.image:
        return '[Imagem]';
      case AttachmentType.document:
        return '[Documento]';
      case AttachmentType.location:
        return '[Localizacao]';
      case AttachmentType.other:
        return '[Anexo]';
    }
  }

  String _messageAuthorForReply(Message message) {
    if (message.senderType == MessageSenderType.system) return 'Sistema';
    final author = message.authorName.trim();
    return author.isEmpty ? 'Contato' : author;
  }

  String _truncateText(String value, {required int maxChars}) {
    if (value.length <= maxChars) return value;
    return '${value.substring(0, maxChars)}...';
  }

  Future<void> _handleSend() async {
    final typedText = _messageController.text.trim();
    if (typedText.isEmpty) return;

    var outgoingText = typedText;
    final replyingTo = _replyingToMessage;
    if (replyingTo != null) {
      outgoingText =
          '${_ReplyPayload.preferredPrefix}${_messageAuthorForReply(replyingTo)}: ${_messagePreviewText(replyingTo)}\n$typedText';
    }

    try {
      await ref
          .read(chatActionsProvider)
          .sendMessage(
            conversationId: widget.conversationId,
            text: outgoingText,
          );
      _requestScrollToBottomAfterSending();
      _messageController.clear();
      if (mounted && replyingTo != null) {
        setState(() {
          _replyingToMessage = null;
        });
      }
    } catch (error) {
      if (!mounted) return;
      ScaffoldMessenger.of(
        context,
      ).showSnackBar(SnackBar(content: Text(error.toString())));
    }
  }

  Future<void> _onMenuAction(
    _ChatMenuAction action, {
    required String contactName,
    required ConversationCapabilities capabilities,
  }) async {
    switch (action) {
      case _ChatMenuAction.search:
        await Navigator.of(context).push(
          MaterialPageRoute(
            builder: (_) => ChatSearchPage(
              conversationId: widget.conversationId,
              contactName: contactName,
            ),
          ),
        );
        break;
      case _ChatMenuAction.close:
        if (!capabilities.canClose) {
          _showFeedback('Finalizacao indisponivel para esta conversa.');
          return;
        }
        final shouldClose = await _confirmCloseConversation();
        if (!shouldClose) return;
        await ref
            .read(chatActionsProvider)
            .closeConversation(widget.conversationId);
        if (!mounted) return;
        context.go(AppRoutes.inbox);
        break;
      case _ChatMenuAction.transfer:
        if (!capabilities.canTransfer) {
          _showFeedback('Transferencia indisponivel para esta conversa.');
          return;
        }
        final targetAgent = await _selectTransferTarget();
        if (targetAgent == null) return;
        await ref
            .read(chatActionsProvider)
            .transferConversation(
              conversationId: widget.conversationId,
              targetAgent: targetAgent,
            );
        _showFeedback('Atendimento transferido para $targetAgent.');
        break;
      case _ChatMenuAction.media:
        await Navigator.of(context).push(
          MaterialPageRoute(
            builder: (_) =>
                ChatMediaLinksDocsPage(conversationId: widget.conversationId),
          ),
        );
        break;
      case _ChatMenuAction.favorites:
        final selectedMessageId = await Navigator.of(context).push<String>(
          MaterialPageRoute(
            builder: (_) =>
                ChatFavoritesPage(conversationId: widget.conversationId),
          ),
        );
        if (selectedMessageId != null && mounted) {
          _focusFavoriteMessage(selectedMessageId);
        }
        break;
      case _ChatMenuAction.notes:
        await Navigator.of(context).push(
          MaterialPageRoute(
            builder: (_) =>
                ChatNotesPage(conversationId: widget.conversationId),
          ),
        );
        break;
    }
  }

  Future<bool> _confirmCloseConversation() async {
    final result = await showDialog<bool>(
      context: context,
      builder: (dialogContext) {
        return AlertDialog(
          title: const Text('Finalizar atendimento'),
          content: const Text('Deseja realmente finalizar este atendimento?'),
          actions: [
            TextButton(
              onPressed: () => Navigator.of(dialogContext).pop(false),
              child: const Text('Cancelar'),
            ),
            FilledButton(
              onPressed: () => Navigator.of(dialogContext).pop(true),
              style: FilledButton.styleFrom(
                backgroundColor: AppColors.primary,
                foregroundColor: Colors.white,
              ),
              child: const Text('Finalizar'),
            ),
          ],
        );
      },
    );
    return result ?? false;
  }

  Future<String?> _selectTransferTarget() async {
    const targets = <String>[
      'Fila Comercial',
      'Financeiro',
      'Suporte Nivel 2',
      'Rafael',
      'Julia',
    ];

    return showModalBottomSheet<String>(
      context: context,
      showDragHandle: true,
      backgroundColor: const Color(0xFFF8F9FB),
      builder: (sheetContext) {
        return SafeArea(
          child: Padding(
            padding: const EdgeInsets.fromLTRB(14, 6, 14, 14),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Text(
                  'Transferir atendimento',
                  style: TextStyle(
                    color: Color(0xFF111827),
                    fontSize: 18,
                    fontWeight: FontWeight.w700,
                  ),
                ),
                const SizedBox(height: 10),
                const Text(
                  'Selecione o colaborador ou fila de destino:',
                  style: TextStyle(color: Color(0xFF5E6B7D), fontSize: 14),
                ),
                const SizedBox(height: 8),
                SizedBox(
                  height: 260,
                  child: ListView.builder(
                    itemCount: targets.length,
                    itemBuilder: (context, index) {
                      final target = targets[index];
                      return ListTile(
                        contentPadding: EdgeInsets.zero,
                        leading: const Icon(Icons.compare_arrows_rounded),
                        title: Text(target),
                        onTap: () => Navigator.of(sheetContext).pop(target),
                      );
                    },
                  ),
                ),
              ],
            ),
          ),
        );
      },
    );
  }

  Future<void> _openQuickActionsMenu() async {
    if (_isAudioRecording) {
      await _cancelAudioRecording();
    }
    FocusScope.of(context).unfocus();
    if (_isEmojiPickerVisible) {
      setState(() {
        _isEmojiPickerVisible = false;
      });
    }
    setState(() {
      _isQuickActionsMenuOpen = true;
    });

    final selected = await showModalBottomSheet<_ChatQuickAction>(
      context: context,
      backgroundColor: Colors.transparent,
      builder: (sheetContext) {
        return _ChatQuickActionsSheet(
          onSelected: (action) => Navigator.of(sheetContext).pop(action),
        );
      },
    );

    if (!mounted) return;
    setState(() {
      _isQuickActionsMenuOpen = false;
    });

    if (selected == null) return;
    await _handleQuickAction(selected);
  }

  Future<void> _handleQuickAction(_ChatQuickAction action) async {
    switch (action) {
      case _ChatQuickAction.documents:
        await _pickAndSendDocumentFromDevice();
        break;
      case _ChatQuickAction.photosVideos:
        final gallerySelection = await _selectMediaKind(fromCamera: false);
        if (gallerySelection == null) return;
        if (gallerySelection == _MediaKind.image) {
          await _pickAndSendImageFromGallery();
        } else {
          await _pickAndSendVideoFromGallery();
        }
        break;
      case _ChatQuickAction.camera:
        final cameraSelection = await _selectMediaKind(fromCamera: true);
        if (cameraSelection == null) return;
        if (cameraSelection == _MediaKind.image) {
          await _captureAndSendImage();
        } else {
          await _captureAndSendVideo();
        }
        break;
      case _ChatQuickAction.currentLocation:
        await _sendCurrentLocation();
        break;
      case _ChatQuickAction.companyLocation:
        await _sendCompanyLocation();
        break;
      case _ChatQuickAction.contact:
        await _pickAndSendPhoneContact();
        break;
      case _ChatQuickAction.internalNote:
        await Navigator.of(context).push(
          MaterialPageRoute(
            builder: (_) =>
                ChatNotesPage(conversationId: widget.conversationId),
          ),
        );
        break;
      case _ChatQuickAction.stickers:
        await _sendAttachmentMessage(
          attachment: _buildMockAttachment(
            fileName: 'figurinha_${DateTime.now().millisecondsSinceEpoch}.webp',
            type: AttachmentType.image,
            sizeKb: 110,
            url: 'mock://stickers/default.webp',
          ),
          successText: 'Figurinha enviada.',
        );
        break;
    }
  }

  Future<void> _sendAttachmentMessage({
    required Attachment attachment,
    required String successText,
  }) async {
    try {
      await ref
          .read(chatActionsProvider)
          .sendMessage(
            conversationId: widget.conversationId,
            text: '',
            attachments: [attachment],
          );
      if (!mounted) return;
      _requestScrollToBottomAfterSending();
      _showFeedback(successText);
    } catch (error) {
      if (!mounted) return;
      _showFeedback(error.toString());
    }
  }

  Future<void> _sendTextShortcut(
    String text, {
    required String successText,
  }) async {
    try {
      await ref
          .read(chatActionsProvider)
          .sendMessage(conversationId: widget.conversationId, text: text);
      if (!mounted) return;
      _requestScrollToBottomAfterSending();
      _showFeedback(successText);
    } catch (error) {
      if (!mounted) return;
      _showFeedback(error.toString());
    }
  }

  Future<void> _pickAndSendPhoneContact() async {
    final granted = await _ensureContactsPermission();
    if (!granted) return;

    try {
      final picked = await FlutterContacts.openExternalPick();
      if (picked == null) return;

      final phone = await _pickPhoneNumber(picked);
      if (phone == null) {
        if (!mounted) return;
        _showFeedback('O contato selecionado nao possui telefone.');
        return;
      }

      final name = picked.displayName.trim().isNotEmpty
          ? picked.displayName.trim()
          : 'Contato sem nome';
      final number = _phoneValue(phone);

      await _sendTextShortcut(
        'Contato compartilhado:\n$name\n$number',
        successText: 'Contato compartilhado.',
      );
    } catch (_) {
      if (!mounted) return;
      _showFeedback('Nao foi possivel selecionar um contato.');
    }
  }

  Future<bool> _ensureContactsPermission() async {
    final granted = await FlutterContacts.requestPermission(readonly: true);
    if (granted) return true;

    final status = await Permission.contacts.status;
    await _showPermissionDeniedFeedback(
      resourceLabel: 'contatos',
      permanentlyDenied: status.isPermanentlyDenied,
    );
    return false;
  }

  Future<Phone?> _pickPhoneNumber(Contact contact) async {
    final phones = contact.phones
        .where((phone) => _phoneValue(phone).isNotEmpty)
        .toList(growable: false);
    if (phones.isEmpty) return null;
    if (phones.length == 1) return phones.first;

    return showModalBottomSheet<Phone>(
      context: context,
      showDragHandle: true,
      backgroundColor: const Color(0xFFF8F9FB),
      builder: (sheetContext) {
        return SafeArea(
          child: Padding(
            padding: const EdgeInsets.fromLTRB(14, 6, 14, 14),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Text(
                  'Escolha o numero',
                  style: TextStyle(
                    color: Color(0xFF111827),
                    fontSize: 18,
                    fontWeight: FontWeight.w700,
                  ),
                ),
                const SizedBox(height: 8),
                Text(
                  contact.displayName.trim().isEmpty
                      ? 'Contato sem nome'
                      : contact.displayName.trim(),
                  style: const TextStyle(
                    color: Color(0xFF5E6B7D),
                    fontSize: 14,
                    fontWeight: FontWeight.w500,
                  ),
                ),
                const SizedBox(height: 8),
                SizedBox(
                  height: (phones.length * 72.0)
                      .clamp(
                        72.0,
                        MediaQuery.of(sheetContext).size.height * 0.45,
                      )
                      .toDouble(),
                  child: ListView.builder(
                    itemCount: phones.length,
                    itemBuilder: (context, index) {
                      final phone = phones[index];
                      return ListTile(
                        contentPadding: EdgeInsets.zero,
                        leading: const Icon(Icons.phone_outlined),
                        title: Text(
                          _phoneValue(phone),
                          style: const TextStyle(fontWeight: FontWeight.w600),
                        ),
                        subtitle: Text(_phoneLabel(phone)),
                        onTap: () => Navigator.of(sheetContext).pop(phone),
                      );
                    },
                  ),
                ),
              ],
            ),
          ),
        );
      },
    );
  }

  String _phoneValue(Phone phone) {
    final normalized = phone.normalizedNumber.trim();
    if (normalized.isNotEmpty) return normalized;
    return phone.number.trim();
  }

  String _phoneLabel(Phone phone) {
    switch (phone.label) {
      case PhoneLabel.mobile:
      case PhoneLabel.workMobile:
      case PhoneLabel.iPhone:
        return 'Celular';
      case PhoneLabel.home:
        return 'Residencial';
      case PhoneLabel.work:
      case PhoneLabel.companyMain:
        return 'Trabalho';
      case PhoneLabel.main:
        return 'Principal';
      case PhoneLabel.custom:
        final custom = phone.customLabel.trim();
        return custom.isEmpty ? 'Telefone' : custom;
      default:
        return 'Telefone';
    }
  }

  Future<void> _sendCurrentLocation() async {
    final canShare = await _ensureLocationPermissionAndServices();
    if (!canShare) return;

    try {
      final position = await Geolocator.getCurrentPosition(
        locationSettings: const LocationSettings(
          accuracy: LocationAccuracy.high,
        ),
      );
      await _sendLocationAttachment(
        label: 'Localizacao atual',
        latitude: position.latitude,
        longitude: position.longitude,
        successText: 'Localizacao atual compartilhada.',
      );
    } catch (_) {
      if (!mounted) return;
      _showFeedback('Nao foi possivel obter sua localizacao atual.');
    }
  }

  Future<void> _sendCompanyLocation() async {
    await _sendLocationAttachment(
      label: 'Localizacao da empresa',
      latitude: -23.56310,
      longitude: -46.65434,
      successText: 'Localizacao da empresa compartilhada.',
    );
  }

  Future<bool> _ensureLocationPermissionAndServices() async {
    final serviceEnabled = await Geolocator.isLocationServiceEnabled();
    if (!serviceEnabled) {
      if (!mounted) return false;
      final messenger = ScaffoldMessenger.of(context);
      messenger.hideCurrentSnackBar();
      messenger.showSnackBar(
        SnackBar(
          content: const Text('Ative o GPS para compartilhar a localizacao.'),
          action: SnackBarAction(
            label: 'GPS',
            onPressed: () {
              unawaited(Geolocator.openLocationSettings());
            },
          ),
        ),
      );
      return false;
    }

    var permission = await Geolocator.checkPermission();
    if (permission == LocationPermission.denied) {
      permission = await Geolocator.requestPermission();
    }

    if (permission == LocationPermission.denied) {
      await _showPermissionDeniedFeedback(
        resourceLabel: 'localizacao',
        permanentlyDenied: false,
      );
      return false;
    }

    if (permission == LocationPermission.deniedForever) {
      await _showPermissionDeniedFeedback(
        resourceLabel: 'localizacao',
        permanentlyDenied: true,
      );
      return false;
    }

    return true;
  }

  Future<void> _sendLocationAttachment({
    required String label,
    required double latitude,
    required double longitude,
    required String successText,
  }) async {
    await _sendAttachmentMessage(
      attachment: Attachment(
        id: 'att_${DateTime.now().microsecondsSinceEpoch}',
        fileName: label,
        type: AttachmentType.location,
        sizeKb: 1,
        url: _buildMapsUrl(latitude: latitude, longitude: longitude),
      ),
      successText: successText,
    );
  }

  String _buildMapsUrl({required double latitude, required double longitude}) {
    final lat = latitude.toStringAsFixed(6);
    final lng = longitude.toStringAsFixed(6);
    return 'https://maps.google.com/?q=$lat,$lng';
  }

  Future<void> _pickAndSendDocumentFromDevice() async {
    final granted = await _ensureDocumentPermission();
    if (!granted) return;

    try {
      final result = await FilePicker.platform.pickFiles(
        type: FileType.custom,
        allowedExtensions: _documentExtensions,
        allowMultiple: false,
      );
      if (result == null || result.files.isEmpty) return;

      final picked = result.files.first;
      final path = picked.path?.trim() ?? '';
      if (path.isEmpty) {
        _showFeedback('Nao foi possivel obter o arquivo selecionado.');
        return;
      }

      final file = File(path);
      if (!file.existsSync()) {
        _showFeedback('Arquivo de documento nao encontrado.');
        return;
      }

      final rawSizeKb = (file.lengthSync() / 1024).ceil();
      final sizeKb = rawSizeKb < 1
          ? 1
          : (rawSizeKb > 1024 * 150 ? 1024 * 150 : rawSizeKb);
      final fileName = picked.name.trim().isNotEmpty
          ? picked.name.trim()
          : 'documento_${DateTime.now().millisecondsSinceEpoch}';

      await _sendAttachmentMessage(
        attachment: Attachment(
          id: 'att_${DateTime.now().microsecondsSinceEpoch}',
          fileName: fileName,
          type: AttachmentType.document,
          sizeKb: sizeKb,
          url: path,
        ),
        successText: 'Documento enviado.',
      );
    } catch (_) {
      if (!mounted) return;
      _showFeedback('Nao foi possivel selecionar o documento.');
    }
  }

  Future<_MediaKind?> _selectMediaKind({required bool fromCamera}) {
    return showModalBottomSheet<_MediaKind>(
      context: context,
      showDragHandle: true,
      backgroundColor: const Color(0xFFF8F9FB),
      builder: (sheetContext) {
        final title = fromCamera
            ? 'Escolha o tipo de captura'
            : 'Escolha o tipo de arquivo';
        final imageLabel = fromCamera ? 'Tirar foto' : 'Selecionar foto';
        final videoLabel = fromCamera ? 'Gravar video' : 'Selecionar video';

        return SafeArea(
          child: Padding(
            padding: const EdgeInsets.fromLTRB(14, 6, 14, 14),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  title,
                  style: const TextStyle(
                    color: Color(0xFF111827),
                    fontSize: 18,
                    fontWeight: FontWeight.w700,
                  ),
                ),
                const SizedBox(height: 8),
                ListTile(
                  contentPadding: EdgeInsets.zero,
                  leading: const Icon(Icons.image_outlined),
                  title: Text(imageLabel),
                  onTap: () => Navigator.of(sheetContext).pop(_MediaKind.image),
                ),
                ListTile(
                  contentPadding: EdgeInsets.zero,
                  leading: const Icon(Icons.videocam_outlined),
                  title: Text(videoLabel),
                  onTap: () => Navigator.of(sheetContext).pop(_MediaKind.video),
                ),
              ],
            ),
          ),
        );
      },
    );
  }

  Future<bool> _ensureMediaPermission({required bool includeVideo}) async {
    if (Platform.isIOS) {
      final status = await Permission.photos.request();
      final granted = status.isGranted || status.isLimited;
      if (!granted) {
        await _showPermissionDeniedFeedback(
          resourceLabel: 'galeria de midia',
          permanentlyDenied: status.isPermanentlyDenied,
        );
      }
      return granted;
    }

    final permissions = <Permission>[
      Permission.photos,
      if (includeVideo) Permission.videos,
      Permission.storage,
    ];
    final result = await permissions.request();
    final granted = result.values.any(
      (status) => status.isGranted || status.isLimited,
    );
    if (granted) return true;

    final permanentlyDenied = result.values.any(
      (status) => status.isPermanentlyDenied,
    );
    await _showPermissionDeniedFeedback(
      resourceLabel: 'arquivos de midia',
      permanentlyDenied: permanentlyDenied,
    );
    return false;
  }

  Future<bool> _ensureDocumentPermission() async {
    // For document picking we rely on the platform file picker (SAF on Android),
    // which does not require broad storage runtime permission.
    return true;
  }

  Future<bool> _ensureCameraPermission() async {
    final cameraStatus = await Permission.camera.request();
    final granted = cameraStatus.isGranted;
    if (!granted) {
      await _showPermissionDeniedFeedback(
        resourceLabel: 'camera',
        permanentlyDenied: cameraStatus.isPermanentlyDenied,
      );
    }
    return granted;
  }

  Future<void> _showPermissionDeniedFeedback({
    required String resourceLabel,
    required bool permanentlyDenied,
  }) async {
    if (!mounted) return;
    final messenger = ScaffoldMessenger.of(context);
    messenger.hideCurrentSnackBar();
    messenger.showSnackBar(
      SnackBar(
        content: Text(
          permanentlyDenied
              ? 'Permissao de $resourceLabel negada. Abra os ajustes para liberar.'
              : 'Permissao de $resourceLabel negada.',
        ),
        action: permanentlyDenied
            ? SnackBarAction(
                label: 'Ajustes',
                onPressed: () {
                  unawaited(openAppSettings());
                },
              )
            : null,
      ),
    );
  }

  Future<void> _pickAndSendImageFromGallery() async {
    final granted = await _ensureMediaPermission(includeVideo: false);
    if (!granted) return;

    try {
      final picked = await _imagePicker.pickImage(
        source: ImageSource.gallery,
        imageQuality: 85,
      );
      if (picked == null) return;
      await _sendPickedImageAttachment(
        picked,
        successText: 'Imagem enviada da galeria.',
      );
    } catch (_) {
      if (!mounted) return;
      _showFeedback('Nao foi possivel abrir a galeria.');
    }
  }

  Future<void> _captureAndSendImage() async {
    final cameraGranted = await _ensureCameraPermission();
    if (!cameraGranted) return;

    try {
      final picked = await _imagePicker.pickImage(
        source: ImageSource.camera,
        preferredCameraDevice: CameraDevice.rear,
        imageQuality: 85,
      );
      if (picked == null) return;
      await _sendPickedImageAttachment(
        picked,
        successText: 'Foto capturada e enviada.',
      );
    } catch (_) {
      if (!mounted) return;
      _showFeedback('Nao foi possivel abrir a camera.');
    }
  }

  Future<void> _pickAndSendVideoFromGallery() async {
    final granted = await _ensureMediaPermission(includeVideo: true);
    if (!granted) return;

    try {
      final picked = await _imagePicker.pickVideo(
        source: ImageSource.gallery,
        maxDuration: const Duration(minutes: 5),
      );
      if (picked == null) return;
      await _sendPickedVideoAttachment(
        picked,
        successText: 'Video enviado da galeria.',
      );
    } catch (_) {
      if (!mounted) return;
      _showFeedback('Nao foi possivel selecionar o video.');
    }
  }

  Future<void> _captureAndSendVideo() async {
    final cameraGranted = await _ensureCameraPermission();
    if (!cameraGranted) return;

    try {
      final picked = await _imagePicker.pickVideo(
        source: ImageSource.camera,
        preferredCameraDevice: CameraDevice.rear,
        maxDuration: const Duration(minutes: 5),
      );
      if (picked == null) return;
      await _sendPickedVideoAttachment(
        picked,
        successText: 'Video capturado e enviado.',
      );
    } catch (_) {
      if (!mounted) return;
      _showFeedback('Nao foi possivel gravar o video.');
    }
  }

  Future<void> _sendPickedImageAttachment(
    XFile picked, {
    required String successText,
  }) async {
    final path = picked.path.trim();
    if (path.isEmpty) {
      _showFeedback('Imagem invalida.');
      return;
    }

    final file = File(path);
    if (!file.existsSync()) {
      _showFeedback('Arquivo de imagem nao encontrado.');
      return;
    }

    final rawSizeKb = (file.lengthSync() / 1024).ceil();
    final sizeKb = rawSizeKb < 1
        ? 1
        : (rawSizeKb > 1024 * 50 ? 1024 * 50 : rawSizeKb);
    final pickedName = picked.name.trim();
    final fileName = pickedName.isNotEmpty
        ? pickedName
        : 'imagem_${DateTime.now().millisecondsSinceEpoch}.jpg';

    await _sendAttachmentMessage(
      attachment: Attachment(
        id: 'att_${DateTime.now().microsecondsSinceEpoch}',
        fileName: fileName,
        type: AttachmentType.image,
        sizeKb: sizeKb,
        url: path,
      ),
      successText: successText,
    );
  }

  Future<void> _sendPickedVideoAttachment(
    XFile picked, {
    required String successText,
  }) async {
    final path = picked.path.trim();
    if (path.isEmpty) {
      _showFeedback('Video invalido.');
      return;
    }

    final file = File(path);
    if (!file.existsSync()) {
      _showFeedback('Arquivo de video nao encontrado.');
      return;
    }

    final rawSizeKb = (file.lengthSync() / 1024).ceil();
    final sizeKb = rawSizeKb < 1
        ? 1
        : (rawSizeKb > 1024 * 150 ? 1024 * 150 : rawSizeKb);
    final pickedName = picked.name.trim();
    final fileName = pickedName.isNotEmpty
        ? pickedName
        : 'video_${DateTime.now().millisecondsSinceEpoch}.mp4';

    await _sendAttachmentMessage(
      attachment: Attachment(
        id: 'att_${DateTime.now().microsecondsSinceEpoch}',
        fileName: fileName,
        type: AttachmentType.video,
        sizeKb: sizeKb,
        url: path,
      ),
      successText: successText,
    );
  }

  Future<void> _sendAudioNote() async {
    if (_hasPendingAudioDraft) {
      await _sendPendingAudioDraft();
      return;
    }
    if (_isAudioRecording) {
      await _stopAudioRecordingForPreview();
      return;
    }
    await _startAudioRecording();
  }

  Future<void> _startAudioRecording() async {
    if (_isAudioRecording) return;

    FocusScope.of(context).unfocus();
    if (_isEmojiPickerVisible) {
      setState(() {
        _isEmojiPickerVisible = false;
      });
    }

    if (_hasPendingAudioDraft) {
      await _discardAudioDraft(deleteFile: true);
    }

    final hasPermission = await _audioRecorder.hasPermission(request: true);
    if (!hasPermission) {
      _showFeedback('Permita o uso do microfone para gravar audios.');
      return;
    }

    final directory = await getTemporaryDirectory();
    final outputPath =
        '${directory.path}/audio_${DateTime.now().millisecondsSinceEpoch}.m4a';

    try {
      await _audioRecorder.start(
        const RecordConfig(
          encoder: AudioEncoder.aacLc,
          bitRate: 64000,
          sampleRate: 44100,
        ),
        path: outputPath,
      );
    } catch (_) {
      _showFeedback('Nao foi possivel iniciar a gravacao de audio.');
      return;
    }

    _audioRecordingTicker?.cancel();
    _audioRecordingTicker = Timer.periodic(const Duration(seconds: 1), (_) {
      if (!mounted || !_isAudioRecording || _isAudioRecordingPaused) return;
      setState(() {
        _audioRecordingDuration += const Duration(seconds: 1);
      });
    });

    if (!mounted) return;
    setState(() {
      _isAudioRecording = true;
      _isAudioRecordingPaused = false;
      _audioRecordingDuration = Duration.zero;
      _audioDraftPath = null;
      _audioDraftDuration = Duration.zero;
      _audioDraftPosition = Duration.zero;
      _audioDraftSpeed = 1.0;
      _isAudioDraftPlaying = false;
      _isAudioDraftPreparing = false;
      _hasAudioDraftLoadError = false;
    });
  }

  Future<void> _pauseAudioRecording() async {
    if (!_isAudioRecording || _isAudioRecordingPaused) return;
    try {
      await _audioRecorder.pause();
    } catch (_) {
      _showFeedback('Nao foi possivel pausar a gravacao.');
      return;
    }
    if (!mounted) return;
    setState(() {
      _isAudioRecordingPaused = true;
    });
  }

  Future<void> _resumeAudioRecording() async {
    if (!_isAudioRecording || !_isAudioRecordingPaused) return;
    try {
      await _audioRecorder.resume();
    } catch (_) {
      _showFeedback('Nao foi possivel retomar a gravacao.');
      return;
    }
    if (!mounted) return;
    setState(() {
      _isAudioRecordingPaused = false;
    });
  }

  Future<void> _stopAudioRecordingForPreview() async {
    if (!_isAudioRecording) return;

    String? recordedPath;
    try {
      recordedPath = await _audioRecorder.stop();
    } catch (_) {
      recordedPath = null;
    }
    _audioRecordingTicker?.cancel();

    final recordedDuration = _audioRecordingDuration;

    if (!mounted) return;
    setState(() {
      _isAudioRecording = false;
      _isAudioRecordingPaused = false;
      _audioRecordingDuration = Duration.zero;
    });

    if (recordedPath == null || recordedPath.isEmpty) {
      _showFeedback('Nao foi possivel finalizar a gravacao.');
      return;
    }

    final audioFile = File(recordedPath);
    if (!audioFile.existsSync()) {
      _showFeedback('Arquivo de audio nao encontrado.');
      return;
    }

    if (!mounted) return;
    setState(() {
      _audioDraftPath = recordedPath;
      _audioDraftDuration = recordedDuration;
      _audioDraftPosition = Duration.zero;
      _audioDraftSpeed = 1.0;
      _isAudioDraftPlaying = false;
      _isAudioDraftPreparing = true;
      _hasAudioDraftLoadError = false;
    });
    await _prepareAudioDraftPreview(recordedPath);
  }

  Future<void> _cancelAudioRecording() async {
    if (!_isAudioRecording) return;
    try {
      await _audioRecorder.cancel();
    } catch (_) {
      // Ignore cancellation errors.
    }
    _audioRecordingTicker?.cancel();
    if (!mounted) return;
    setState(() {
      _isAudioRecording = false;
      _isAudioRecordingPaused = false;
      _audioRecordingDuration = Duration.zero;
    });
  }

  Future<void> _prepareAudioDraftPreview(String path) async {
    try {
      await _audioDraftPlayer.stop();
      await _audioDraftPlayer.setFilePath(path);
      await _audioDraftPlayer.setSpeed(_audioDraftSpeed);
      if (!mounted) return;
      setState(() {
        _isAudioDraftPreparing = false;
        _hasAudioDraftLoadError = false;
      });
    } catch (_) {
      if (!mounted) return;
      setState(() {
        _isAudioDraftPreparing = false;
        _hasAudioDraftLoadError = true;
      });
    }
  }

  Future<void> _toggleAudioDraftPlayback() async {
    if (_audioDraftPath == null || _isAudioDraftPreparing) return;
    if (_hasAudioDraftLoadError) {
      await _prepareAudioDraftPreview(_audioDraftPath!);
      if (_hasAudioDraftLoadError) return;
    }
    if (_isAudioDraftPlaying) {
      await _audioDraftPlayer.pause();
      return;
    }
    if (_audioDraftDuration > Duration.zero &&
        _audioDraftPosition >= _audioDraftDuration) {
      await _audioDraftPlayer.seek(Duration.zero);
    }
    await _audioDraftPlayer.play();
  }

  Future<void> _toggleAudioDraftSpeed() async {
    if (_audioDraftPath == null) return;
    final nextSpeed = _audioDraftSpeed == 1.0
        ? 1.5
        : (_audioDraftSpeed == 1.5 ? 2.0 : 1.0);
    try {
      await _audioDraftPlayer.setSpeed(nextSpeed);
      if (!mounted) return;
      setState(() {
        _audioDraftSpeed = nextSpeed;
      });
    } catch (_) {
      // Ignore speed errors on unsupported platforms.
    }
  }

  Future<void> _discardAudioDraft({required bool deleteFile}) async {
    final draftPath = _audioDraftPath;
    await _audioDraftPlayer.stop();
    if (mounted) {
      setState(() {
        _audioDraftPath = null;
        _audioDraftDuration = Duration.zero;
        _audioDraftPosition = Duration.zero;
        _audioDraftSpeed = 1.0;
        _isAudioDraftPlaying = false;
        _isAudioDraftPreparing = false;
        _hasAudioDraftLoadError = false;
      });
    }
    if (deleteFile && draftPath != null) {
      final file = File(draftPath);
      if (file.existsSync()) {
        try {
          await file.delete();
        } catch (_) {
          // Ignore delete failures.
        }
      }
    }
  }

  Future<void> _sendPendingAudioDraft() async {
    final draftPath = _audioDraftPath;
    if (draftPath == null) return;

    await _audioDraftPlayer.pause();

    final audioFile = File(draftPath);
    if (!audioFile.existsSync()) {
      _showFeedback('Arquivo de audio nao encontrado.');
      await _discardAudioDraft(deleteFile: false);
      return;
    }

    final rawSizeKb = (audioFile.lengthSync() / 1024).ceil();
    final sizeKb = rawSizeKb < 1
        ? 1
        : (rawSizeKb > 1024 * 50 ? 1024 * 50 : rawSizeKb);
    final durationForMessage = _audioDraftDuration > Duration.zero
        ? _audioDraftDuration
        : _audioRecordingDuration;

    try {
      await ref
          .read(chatActionsProvider)
          .sendMessage(
            conversationId: widget.conversationId,
            text: '',
            attachments: [
              Attachment(
                id: 'att_${DateTime.now().microsecondsSinceEpoch}',
                fileName: 'audio_${DateTime.now().millisecondsSinceEpoch}.m4a',
                type: AttachmentType.audio,
                sizeKb: sizeKb,
                url: draftPath,
              ),
            ],
          );
      if (!mounted) return;
      _requestScrollToBottomAfterSending();
      _showFeedback('Audio enviado (${_formatDuration(durationForMessage)}).');
      await _discardAudioDraft(deleteFile: false);
    } catch (error) {
      if (!mounted) return;
      _showFeedback(error.toString());
    }
  }

  String _formatDuration(Duration duration) {
    return _formatClockDuration(duration);
  }

  String _formatAudioSpeed(double speed) {
    return _formatAudioSpeedLabel(speed);
  }

  void _toggleEmojiPicker() {
    if (_isAudioRecording || _hasPendingAudioDraft) {
      _showFeedback('Finalize ou cancele o audio para abrir emojis.');
      return;
    }
    if (_isEmojiPickerVisible) {
      setState(() {
        _isEmojiPickerVisible = false;
      });
      _messageFocusNode.requestFocus();
      return;
    }

    _messageFocusNode.unfocus();
    setState(() {
      _isEmojiPickerVisible = true;
    });
  }

  void _onEmojiBackspacePressed() {
    final text = _messageController.text;
    final selection = _messageController.selection;
    if (text.isEmpty) return;

    int start = selection.start;
    int end = selection.end;

    if (start < 0 || end < 0) {
      start = text.length;
      end = text.length;
    }

    if (start != end) {
      final newText = text.replaceRange(start, end, '');
      _messageController.value = TextEditingValue(
        text: newText,
        selection: TextSelection.collapsed(offset: start),
      );
      return;
    }

    if (start == 0) return;

    final leftText = text.substring(0, start);
    final rightText = text.substring(start);
    final leftChars = leftText.characters;
    final keepCount = leftChars.length - 1;
    final newLeft = keepCount > 0 ? leftChars.take(keepCount).toString() : '';
    final newText = '$newLeft$rightText';
    final newCursor = newLeft.length;

    _messageController.value = TextEditingValue(
      text: newText,
      selection: TextSelection.collapsed(offset: newCursor),
    );
  }

  Future<bool> _handleChatWillPop() async {
    if (_isSelectionMode) {
      _clearSelection();
      return false;
    }
    if (_isEmojiPickerVisible) {
      setState(() {
        _isEmojiPickerVisible = false;
      });
      return false;
    }
    return true;
  }

  Attachment _buildMockAttachment({
    required String fileName,
    required AttachmentType type,
    required int sizeKb,
    required String url,
  }) {
    return Attachment(
      id: 'att_${DateTime.now().microsecondsSinceEpoch}',
      fileName: fileName,
      type: type,
      sizeKb: sizeKb,
      url: url,
    );
  }

  void _showFeedback(String text) {
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(text)));
  }

  @override
  Widget build(BuildContext context) {
    final conversationAsync = ref.watch(
      conversationByIdProvider(widget.conversationId),
    );
    final currentUser = ref.watch(
      authSessionProvider.select((session) => session.user),
    );
    final currentUserName = currentUser?.name ?? '';
    final currentUserId = currentUser?.id ?? 'local_mobile_user';

    return conversationAsync.when(
      data: (conversation) {
        if (conversation == null) {
          return const LeroEmptyState(
            title: 'Conversa nao encontrada',
            message: 'Nao foi possivel abrir este atendimento.',
            icon: Icons.error_outline,
          );
        }

        return WillPopScope(
          onWillPop: _handleChatWillPop,
          child: Container(
            color: const Color(0xFFF0F2F5),
            child: Column(
              children: [
                Container(
                  height: MediaQuery.of(context).padding.top,
                  color: Colors.white,
                ),
                if (_isSelectionMode)
                  _ChatSelectionHeaderSection(
                    conversationId: widget.conversationId,
                    selectedMessageIds: _selectedMessageIds,
                    onBack: _clearSelection,
                    onReplyToMessage: (message) {
                      unawaited(_replyToMessage(message));
                    },
                    onToggleFavoriteSelection: (selectedItems) {
                      unawaited(_toggleFavoriteSelection(selectedItems));
                    },
                    onDeleteSelection: (items, selectedItems) {
                      unawaited(_deleteSelection(items, selectedItems));
                    },
                    onCopySelection: (selectedItems) {
                      unawaited(_copySelection(selectedItems));
                    },
                    onForwardSelection: (messages) {
                      unawaited(_forwardMessages(messages));
                    },
                  )
                else
                  _ChatHeader(
                    contactName: conversation.contactName,
                    avatar: conversation.contactAvatarUrl,
                    capabilities: conversation.capabilities,
                    canOpenContact:
                        conversation.channel == ConversationChannel.whatsapp,
                    onBack: () {
                      final isInternalConversation =
                          conversation.channel ==
                              ConversationChannel.internalCollaborator ||
                          conversation.channel ==
                              ConversationChannel.internalTeam;
                      context.go(
                        isInternalConversation
                            ? AppRoutes.internalChat
                            : AppRoutes.inbox,
                      );
                    },
                    onOpenContact: () {
                      if (conversation.contactId.trim().isEmpty) return;
                      context.push(AppRoutes.contact(conversation.contactId));
                    },
                    onMenuAction: (action) => _onMenuAction(
                      action,
                      contactName: conversation.contactName,
                      capabilities: conversation.capabilities,
                    ),
                  ),
                Expanded(
                  child: GestureDetector(
                    behavior: HitTestBehavior.translucent,
                    onTap: _isSelectionMode ? _clearSelection : null,
                    child: _ChatMessagesSection(
                      conversationId: widget.conversationId,
                      selectedMessageIds: _selectedMessageIds,
                      highlightedMessageId: _highlightedMessageId,
                      isSelectionMode: _isSelectionMode,
                      messagesScrollController: _messagesScrollController,
                      showDownloadBar: _showDownloadBar,
                      showScrollToBottom: _showScrollToBottom,
                      selectedTime: _selectedTime,
                      onSyncMessagesAfterBuild: _syncMessagesAfterBuild,
                      onMessageTap: _handleMessageTap,
                      onMessageLongPress: _handleMessageLongPress,
                      onToggleFavoriteMessage: (messageId) {
                        ref
                            .read(favoriteMessageIdsProvider.notifier)
                            .toggleFavorite(messageId);
                      },
                      onApplyReaction: (item, emoji) {
                        unawaited(
                          _applyReaction(
                            item,
                            emoji,
                            userId: currentUserId,
                            userName: currentUserName,
                          ),
                        );
                      },
                      onOpenReactionPicker: (item) {
                        unawaited(
                          _openReactionPicker(
                            item,
                            userId: currentUserId,
                            userName: currentUserName,
                          ),
                        );
                      },
                      onScrollToBottom: () => _scrollToBottom(animated: true),
                      onCloseDownloadBar: () {
                        setState(() {
                          _showDownloadBar = false;
                        });
                      },
                      messageKeyFor: _messageKeyFor,
                      isCurrentUserMessage: (message) => _isCurrentUserMessage(
                        message: message,
                        currentUserName: currentUserName,
                      ),
                    ),
                  ),
                ),
                if (!conversation.isConnectionReady)
                  _ConnectionAvailabilityBanner(
                    message:
                        'A conexao ${conversation.connectionName} nao esta pronta para envio. Escolha uma conexao ativa no workspace para voltar a responder.',
                  ),
                if (_replyingToMessage != null)
                  _ReplyComposerBar(
                    author: _messageAuthorForReply(_replyingToMessage!),
                    preview: _messagePreviewText(_replyingToMessage!),
                    onCancel: () {
                      setState(() {
                        _replyingToMessage = null;
                      });
                    },
                  ),
                _ChatComposerSection(
                  conversation: conversation,
                  messageController: _messageController,
                  messageFocusNode: _messageFocusNode,
                  isQuickActionsMenuOpen: _isQuickActionsMenuOpen,
                  isAudioRecording: _isAudioRecording,
                  hasPendingAudioDraft: _hasPendingAudioDraft,
                  isAudioRecordingPaused: _isAudioRecordingPaused,
                  isAudioDraftPreparing: _isAudioDraftPreparing,
                  hasAudioDraftLoadError: _hasAudioDraftLoadError,
                  isAudioDraftPlaying: _isAudioDraftPlaying,
                  audioRecordingDuration: _audioRecordingDuration,
                  audioDraftDuration: _audioDraftDuration,
                  audioDraftPosition: _audioDraftPosition,
                  audioDraftSpeed: _audioDraftSpeed,
                  onToggleEmojiPicker: _toggleEmojiPicker,
                  onShowFeedback: _showFeedback,
                  onOpenQuickActionsMenu: () {
                    unawaited(_openQuickActionsMenu());
                  },
                  onSendAudioNote: () {
                    unawaited(_sendAudioNote());
                  },
                  onHandleSend: () {
                    unawaited(_handleSend());
                  },
                  onCancelAudioRecording: () {
                    unawaited(_cancelAudioRecording());
                  },
                  onDiscardAudioDraft: () {
                    unawaited(_discardAudioDraft(deleteFile: true));
                  },
                  onResumeAudioRecording: () {
                    unawaited(_resumeAudioRecording());
                  },
                  onPauseAudioRecording: () {
                    unawaited(_pauseAudioRecording());
                  },
                  onStopAudioRecordingForPreview: () {
                    unawaited(_stopAudioRecordingForPreview());
                  },
                  onToggleAudioDraftPlayback: () {
                    unawaited(_toggleAudioDraftPlayback());
                  },
                  onToggleAudioDraftSpeed: () {
                    unawaited(_toggleAudioDraftSpeed());
                  },
                  onSendPendingAudioDraft: () {
                    unawaited(_sendPendingAudioDraft());
                  },
                ),
                AnimatedContainer(
                  duration: const Duration(milliseconds: 170),
                  height: _isEmojiPickerVisible ? 320 : 0,
                  curve: Curves.easeOut,
                  child: _isEmojiPickerVisible
                      ? EmojiPicker(
                          textEditingController: _messageController,
                          onBackspacePressed: _onEmojiBackspacePressed,
                          config: Config(
                            height: 320,
                            checkPlatformCompatibility: true,
                            emojiViewConfig: EmojiViewConfig(
                              backgroundColor: const Color(0xFFF7F8FA),
                              columns: 8,
                              emojiSizeMax:
                                  28 *
                                  (foundation.defaultTargetPlatform ==
                                          TargetPlatform.iOS
                                      ? 1.2
                                      : 1.0),
                            ),
                            viewOrderConfig: const ViewOrderConfig(
                              top: EmojiPickerItem.categoryBar,
                              middle: EmojiPickerItem.emojiView,
                              bottom: EmojiPickerItem.searchBar,
                            ),
                            skinToneConfig: const SkinToneConfig(
                              enabled: true,
                              indicatorColor: AppColors.primary,
                              dialogBackgroundColor: Colors.white,
                            ),
                            categoryViewConfig: const CategoryViewConfig(
                              backgroundColor: Color(0xFFF7F8FA),
                              iconColor: Color(0xFF6D7584),
                              iconColorSelected: AppColors.primary,
                              indicatorColor: AppColors.primary,
                              backspaceColor: AppColors.primary,
                            ),
                            bottomActionBarConfig: const BottomActionBarConfig(
                              backgroundColor: Color(0xFFF7F8FA),
                              buttonColor: Color(0xFFF7F8FA),
                              buttonIconColor: Color(0xFF6D7584),
                              showBackspaceButton: true,
                              showSearchViewButton: true,
                            ),
                            searchViewConfig: const SearchViewConfig(
                              backgroundColor: Color(0xFFF7F8FA),
                              buttonIconColor: Color(0xFF6D7584),
                              hintText: 'Pesquisar emoji',
                            ),
                          ),
                        )
                      : const SizedBox.shrink(),
                ),
              ],
            ),
          ),
        );
      },
      loading: () => const Center(child: CircularProgressIndicator()),
      error: (error, _) =>
          Center(child: LeroErrorBanner(message: error.toString())),
    );
  }

  bool _isCurrentUserMessage({
    required Message message,
    required String currentUserName,
  }) {
    if (message.senderType == MessageSenderType.system) return false;
    if (message.direction == MessageDirection.outbound) return true;
    if (message.senderType == MessageSenderType.contact) return false;

    final normalizedCurrentUser = currentUserName.trim().toLowerCase();
    final normalizedAuthor = message.authorName.trim().toLowerCase();

    if (normalizedCurrentUser.isEmpty || normalizedAuthor.isEmpty) {
      return message.senderType == MessageSenderType.agent;
    }

    return normalizedAuthor == normalizedCurrentUser;
  }
}

String _formatClockDuration(Duration value) {
  final minutes = value.inMinutes.remainder(60).toString().padLeft(2, '0');
  final seconds = value.inSeconds.remainder(60).toString().padLeft(2, '0');
  return '$minutes:$seconds';
}

bool _isNetworkAttachmentSource(String source) {
  return source.startsWith('http://') || source.startsWith('https://');
}

bool _isLocalAttachmentSource(String source) {
  return source.isNotEmpty &&
      !_isNetworkAttachmentSource(source) &&
      !source.startsWith('mock://');
}

String _formatAudioSpeedLabel(double speed) {
  if ((speed - speed.roundToDouble()).abs() < 0.001) {
    return '${speed.toInt()}x';
  }
  return '${speed.toStringAsFixed(1)}x';
}

class _ChatSelectionHeaderSection extends ConsumerWidget {
  const _ChatSelectionHeaderSection({
    required this.conversationId,
    required this.selectedMessageIds,
    required this.onBack,
    required this.onReplyToMessage,
    required this.onToggleFavoriteSelection,
    required this.onDeleteSelection,
    required this.onCopySelection,
    required this.onForwardSelection,
  });

  final String conversationId;
  final Set<String> selectedMessageIds;
  final VoidCallback onBack;
  final ValueChanged<Message> onReplyToMessage;
  final ValueChanged<List<ChatMessageItem>> onToggleFavoriteSelection;
  final void Function(
    List<ChatMessageItem> items,
    List<ChatMessageItem> selectedItems,
  )
  onDeleteSelection;
  final ValueChanged<List<ChatMessageItem>> onCopySelection;
  final ValueChanged<List<Message>> onForwardSelection;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final messageItemsAsync = ref.watch(chatMessageItemsProvider(conversationId));
    return messageItemsAsync.when(
      data: (items) {
        final selectedItems = items
            .where((item) => selectedMessageIds.contains(item.message.id))
            .toList(growable: false)
          ..sort((a, b) => a.message.sentAt.compareTo(b.message.sentAt));
        final selectedItem = selectedItems.length == 1
            ? selectedItems.first
            : null;
        final canReply = selectedItem?.canReply ?? false;
        final canFavorite = selectedItems.any((item) => item.canFavorite);
        final canDelete = selectedItems.isNotEmpty;
        final canCopy =
            selectedItems.isNotEmpty &&
            selectedItems.every((item) => item.canCopy);
        final canForward =
            selectedItems.isNotEmpty &&
            selectedItems.every((item) => item.canForward);

        return _ChatSelectionHeader(
          count: selectedItems.length,
          canReply: canReply,
          canFavorite: canFavorite,
          canDelete: canDelete,
          canCopy: canCopy,
          canForward: canForward,
          onBack: onBack,
          onReply: canReply ? () => onReplyToMessage(selectedItem!.message) : null,
          onFavorite: canFavorite
              ? () => onToggleFavoriteSelection(selectedItems)
              : null,
          onDelete: canDelete ? () => onDeleteSelection(items, selectedItems) : null,
          onCopy: canCopy ? () => onCopySelection(selectedItems) : null,
          onForward: canForward
              ? () => onForwardSelection(
                  selectedItems
                      .map((item) => item.message)
                      .toList(growable: false),
                )
              : null,
        );
      },
      loading: () => const SizedBox.shrink(),
      error: (_, _) => const SizedBox.shrink(),
    );
  }
}

class _ChatMessagesSection extends ConsumerWidget {
  const _ChatMessagesSection({
    required this.conversationId,
    required this.selectedMessageIds,
    required this.highlightedMessageId,
    required this.isSelectionMode,
    required this.messagesScrollController,
    required this.showDownloadBar,
    required this.showScrollToBottom,
    required this.selectedTime,
    required this.onSyncMessagesAfterBuild,
    required this.onMessageTap,
    required this.onMessageLongPress,
    required this.onToggleFavoriteMessage,
    required this.onApplyReaction,
    required this.onOpenReactionPicker,
    required this.onScrollToBottom,
    required this.onCloseDownloadBar,
    required this.messageKeyFor,
    required this.isCurrentUserMessage,
  });

  final String conversationId;
  final Set<String> selectedMessageIds;
  final String? highlightedMessageId;
  final bool isSelectionMode;
  final ScrollController messagesScrollController;
  final bool showDownloadBar;
  final bool showScrollToBottom;
  final String selectedTime;
  final ValueChanged<List<ChatMessageItem>> onSyncMessagesAfterBuild;
  final ValueChanged<ChatMessageItem> onMessageTap;
  final ValueChanged<ChatMessageItem> onMessageLongPress;
  final ValueChanged<String> onToggleFavoriteMessage;
  final void Function(ChatMessageItem item, String emoji) onApplyReaction;
  final ValueChanged<ChatMessageItem> onOpenReactionPicker;
  final VoidCallback onScrollToBottom;
  final VoidCallback onCloseDownloadBar;
  final GlobalKey Function(String messageId) messageKeyFor;
  final bool Function(Message message) isCurrentUserMessage;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final messageItemsAsync = ref.watch(chatMessageItemsProvider(conversationId));
    return Stack(
      children: [
        const Positioned.fill(child: _ChatPatternBackground()),
        if (isSelectionMode)
          const Positioned.fill(
            child: DecoratedBox(
              decoration: BoxDecoration(color: Color(0x12000000)),
            ),
          ),
        messageItemsAsync.when(
          data: (items) {
            if (items.isEmpty) {
              return const Center(
                child: LeroEmptyState(
                  title: 'Sem mensagens',
                  message: 'Inicie a conversa com o contato.',
                  icon: Icons.chat_bubble_outline,
                ),
              );
            }
            onSyncMessagesAfterBuild(items);
            final selectedItems = items
                .where((item) => selectedMessageIds.contains(item.message.id))
                .toList(growable: false)
              ..sort((a, b) => a.message.sentAt.compareTo(b.message.sentAt));
            final selectedItem = selectedItems.length == 1
                ? selectedItems.first
                : null;

            return ListView.builder(
              controller: messagesScrollController,
              padding: const EdgeInsets.fromLTRB(10, 38, 10, 12),
              itemCount: items.length,
              itemBuilder: (context, index) {
                final item = items[index];
                final message = item.message;
                final isSelected = selectedMessageIds.contains(message.id);
                final showReactionPicker =
                    selectedItem?.message.id == message.id &&
                    selectedItem!.canReact;
                final reactionBar = showReactionPicker
                    ? _MessageReactionPicker(
                        onEmojiSelected: (emoji) => onApplyReaction(item, emoji),
                        onMore: () => onOpenReactionPicker(item),
                      )
                    : null;
                if (message.senderType == MessageSenderType.system) {
                  return KeyedSubtree(
                    key: messageKeyFor(message.id),
                    child: _SystemTimelineCard(message: message),
                  );
                }
                if (isCurrentUserMessage(message)) {
                  return KeyedSubtree(
                    key: messageKeyFor(message.id),
                    child: _AgentTimelineBubble(
                      item: item,
                      isHighlighted: highlightedMessageId == message.id,
                      isSelected: isSelected,
                      reactionPicker: reactionBar,
                      onToggleFavorite: item.canFavorite
                          ? () => onToggleFavoriteMessage(message.id)
                          : null,
                      onTap: () => onMessageTap(item),
                      onLongPress: () => onMessageLongPress(item),
                    ),
                  );
                }
                return KeyedSubtree(
                  key: messageKeyFor(message.id),
                  child: _ContactTimelineBubble(
                    item: item,
                    isHighlighted: highlightedMessageId == message.id,
                    isSelected: isSelected,
                    reactionPicker: reactionBar,
                    onToggleFavorite: item.canFavorite
                        ? () => onToggleFavoriteMessage(message.id)
                        : null,
                    onTap: () => onMessageTap(item),
                    onLongPress: () => onMessageLongPress(item),
                  ),
                );
              },
            );
          },
          loading: () => ListView(
            padding: const EdgeInsets.all(12),
            children: const [
              LeroSkeleton(height: 84),
              SizedBox(height: 10),
              LeroSkeleton(height: 84),
              SizedBox(height: 10),
              LeroSkeleton(height: 84),
            ],
          ),
          error: (error, _) => Padding(
            padding: const EdgeInsets.all(12),
            child: LeroErrorBanner(message: error.toString()),
          ),
        ),
        const Positioned(
          top: 6,
          left: 0,
          right: 0,
          child: Center(child: _TodayBadge()),
        ),
        if (showDownloadBar)
          Positioned(
            left: 14,
            right: 14,
            bottom: 6,
            child: _DownloadBar(time: selectedTime, onClose: onCloseDownloadBar),
          ),
        if (showScrollToBottom)
          Positioned(
            right: 12,
            bottom: showDownloadBar ? 76 : 18,
            child: _ScrollToBottomButton(onTap: onScrollToBottom),
          ),
      ],
    );
  }
}

class _ChatComposerSection extends StatelessWidget {
  const _ChatComposerSection({
    required this.conversation,
    required this.messageController,
    required this.messageFocusNode,
    required this.isQuickActionsMenuOpen,
    required this.isAudioRecording,
    required this.hasPendingAudioDraft,
    required this.isAudioRecordingPaused,
    required this.isAudioDraftPreparing,
    required this.hasAudioDraftLoadError,
    required this.isAudioDraftPlaying,
    required this.audioRecordingDuration,
    required this.audioDraftDuration,
    required this.audioDraftPosition,
    required this.audioDraftSpeed,
    required this.onToggleEmojiPicker,
    required this.onShowFeedback,
    required this.onOpenQuickActionsMenu,
    required this.onSendAudioNote,
    required this.onHandleSend,
    required this.onCancelAudioRecording,
    required this.onDiscardAudioDraft,
    required this.onResumeAudioRecording,
    required this.onPauseAudioRecording,
    required this.onStopAudioRecordingForPreview,
    required this.onToggleAudioDraftPlayback,
    required this.onToggleAudioDraftSpeed,
    required this.onSendPendingAudioDraft,
  });

  final Conversation conversation;
  final TextEditingController messageController;
  final FocusNode messageFocusNode;
  final bool isQuickActionsMenuOpen;
  final bool isAudioRecording;
  final bool hasPendingAudioDraft;
  final bool isAudioRecordingPaused;
  final bool isAudioDraftPreparing;
  final bool hasAudioDraftLoadError;
  final bool isAudioDraftPlaying;
  final Duration audioRecordingDuration;
  final Duration audioDraftDuration;
  final Duration audioDraftPosition;
  final double audioDraftSpeed;
  final VoidCallback onToggleEmojiPicker;
  final ValueChanged<String> onShowFeedback;
  final VoidCallback onOpenQuickActionsMenu;
  final VoidCallback onSendAudioNote;
  final VoidCallback onHandleSend;
  final VoidCallback onCancelAudioRecording;
  final VoidCallback onDiscardAudioDraft;
  final VoidCallback onResumeAudioRecording;
  final VoidCallback onPauseAudioRecording;
  final VoidCallback onStopAudioRecordingForPreview;
  final VoidCallback onToggleAudioDraftPlayback;
  final VoidCallback onToggleAudioDraftSpeed;
  final VoidCallback onSendPendingAudioDraft;

  @override
  Widget build(BuildContext context) {
    if (isAudioRecording || hasPendingAudioDraft) {
      return _VoiceNoteComposer(
        isRecording: isAudioRecording,
        isRecordingPaused: isAudioRecordingPaused,
        isPreparingPreview: isAudioDraftPreparing,
        hasPreviewError: hasAudioDraftLoadError,
        isPreviewPlaying: isAudioDraftPlaying,
        elapsedLabel: _formatClockDuration(
          isAudioRecording ? audioRecordingDuration : audioDraftPosition,
        ),
        totalLabel: _formatClockDuration(
          isAudioRecording ? audioRecordingDuration : audioDraftDuration,
        ),
        speedLabel: _formatAudioSpeedLabel(audioDraftSpeed),
        waveformProgress: audioDraftDuration.inMilliseconds <= 0
            ? 0.0
            : (audioDraftPosition.inMilliseconds /
                      audioDraftDuration.inMilliseconds)
                  .clamp(0, 1)
                  .toDouble(),
        onDiscard: isAudioRecording
            ? onCancelAudioRecording
            : onDiscardAudioDraft,
        onPauseOrResumeRecording: isAudioRecordingPaused
            ? onResumeAudioRecording
            : onPauseAudioRecording,
        onStopRecording: onStopAudioRecordingForPreview,
        onTogglePreviewPlayback: onToggleAudioDraftPlayback,
        onToggleSpeed: onToggleAudioDraftSpeed,
        onSend: onSendPendingAudioDraft,
      );
    }

    final capabilities = conversation.capabilities;
    final canUseQuickActions = capabilities.hasQuickActions;
    final canSendAudio = capabilities.canSendAudio;
    final canSendText = capabilities.canSendText;

    return ChatComposer(
      controller: messageController,
      focusNode: messageFocusNode,
      isPlusEnabled: canUseQuickActions,
      isAudioEnabled: canSendAudio,
      plusHighlighted: isQuickActionsMenuOpen,
      isRecordingAudio: isAudioRecording,
      onEmoji: onToggleEmojiPicker,
      onPlus: () {
        if (!canUseQuickActions) {
          onShowFeedback(
            'Anexos e compartilhamentos estao desabilitados para esta conversa nesta fase.',
          );
          return;
        }
        onOpenQuickActionsMenu();
      },
      onAudio: () {
        if (!canSendAudio) {
          onShowFeedback(
            'Envio de audio desabilitado para esta conversa nesta fase.',
          );
          return;
        }
        onSendAudioNote();
      },
      onSend: () {
        if (!canSendText) {
          onShowFeedback('Envio de texto indisponivel para esta conversa.');
          return;
        }
        onHandleSend();
      },
    );
  }
}

class _VoiceNoteComposer extends StatelessWidget {
  const _VoiceNoteComposer({
    required this.isRecording,
    required this.isRecordingPaused,
    required this.isPreparingPreview,
    required this.hasPreviewError,
    required this.isPreviewPlaying,
    required this.elapsedLabel,
    required this.totalLabel,
    required this.speedLabel,
    required this.waveformProgress,
    required this.onDiscard,
    required this.onPauseOrResumeRecording,
    required this.onStopRecording,
    required this.onTogglePreviewPlayback,
    required this.onToggleSpeed,
    required this.onSend,
  });

  final bool isRecording;
  final bool isRecordingPaused;
  final bool isPreparingPreview;
  final bool hasPreviewError;
  final bool isPreviewPlaying;
  final String elapsedLabel;
  final String totalLabel;
  final String speedLabel;
  final double waveformProgress;
  final VoidCallback onDiscard;
  final VoidCallback onPauseOrResumeRecording;
  final VoidCallback onStopRecording;
  final VoidCallback onTogglePreviewPlayback;
  final VoidCallback onToggleSpeed;
  final VoidCallback onSend;

  @override
  Widget build(BuildContext context) {
    final title = isRecording
        ? (isRecordingPaused ? 'Gravacao pausada' : 'Gravando mensagem de voz')
        : 'Mensagem de voz';
    final timeLabel = isRecording ? totalLabel : '$elapsedLabel / $totalLabel';
    final canPlayPreview = !isPreparingPreview && !hasPreviewError;

    return Container(
      color: const Color(0xFFF0F2F5),
      padding: const EdgeInsets.fromLTRB(8, 6, 8, 8),
      child: SafeArea(
        top: false,
        child: Container(
          padding: const EdgeInsets.fromLTRB(10, 8, 10, 10),
          decoration: BoxDecoration(
            color: const Color(0xFFF97316),
            borderRadius: BorderRadius.circular(14),
          ),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  const Icon(Icons.mic_rounded, size: 16, color: Colors.white),
                  const SizedBox(width: 6),
                  Expanded(
                    child: Text(
                      title,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: const TextStyle(
                        color: Colors.white,
                        fontSize: 15,
                        fontWeight: FontWeight.w700,
                      ),
                    ),
                  ),
                  InkWell(
                    onTap: onDiscard,
                    customBorder: const CircleBorder(),
                    child: const Padding(
                      padding: EdgeInsets.all(4),
                      child: Icon(
                        Icons.delete_outline_rounded,
                        size: 20,
                        color: Colors.white,
                      ),
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 8),
              Row(
                children: [
                  InkWell(
                    onTap: isRecording ? null : onToggleSpeed,
                    borderRadius: BorderRadius.circular(13),
                    child: Container(
                      padding: const EdgeInsets.symmetric(
                        horizontal: 10,
                        vertical: 4,
                      ),
                      decoration: BoxDecoration(
                        color: Colors.white.withOpacity(
                          isRecording ? 0.18 : 0.28,
                        ),
                        borderRadius: BorderRadius.circular(13),
                      ),
                      child: Text(
                        isRecording ? 'REC' : speedLabel,
                        style: const TextStyle(
                          color: Colors.white,
                          fontSize: 12,
                          fontWeight: FontWeight.w700,
                        ),
                      ),
                    ),
                  ),
                  const SizedBox(width: 8),
                  _VoiceActionCircle(
                    icon: isRecording
                        ? (isRecordingPaused
                              ? Icons.mic_rounded
                              : Icons.pause_rounded)
                        : (isPreviewPlaying
                              ? Icons.pause_rounded
                              : Icons.play_arrow_rounded),
                    onTap: isRecording
                        ? onPauseOrResumeRecording
                        : (canPlayPreview ? onTogglePreviewPlayback : null),
                    isLoading: !isRecording && isPreparingPreview,
                  ),
                  if (isRecording) ...[
                    const SizedBox(width: 8),
                    _VoiceActionCircle(
                      icon: Icons.stop_rounded,
                      onTap: onStopRecording,
                    ),
                  ],
                  const SizedBox(width: 8),
                  Expanded(
                    child: _VoiceWaveform(
                      progress: isRecording ? 1 : waveformProgress,
                      isRecording: isRecording,
                    ),
                  ),
                  const SizedBox(width: 8),
                  Text(
                    timeLabel,
                    style: const TextStyle(
                      color: Colors.white,
                      fontSize: 12,
                      fontWeight: FontWeight.w700,
                    ),
                  ),
                  if (!isRecording) ...[
                    const SizedBox(width: 6),
                    InkWell(
                      onTap: onSend,
                      customBorder: const CircleBorder(),
                      child: const Padding(
                        padding: EdgeInsets.all(4),
                        child: Icon(
                          Icons.send_rounded,
                          color: Colors.white,
                          size: 21,
                        ),
                      ),
                    ),
                  ],
                ],
              ),
              if (!isRecording && hasPreviewError) ...[
                const SizedBox(height: 6),
                const Text(
                  'Nao foi possivel reproduzir o audio.',
                  style: TextStyle(
                    color: Colors.white,
                    fontSize: 12,
                    fontWeight: FontWeight.w600,
                  ),
                ),
              ],
            ],
          ),
        ),
      ),
    );
  }
}

class _VoiceActionCircle extends StatelessWidget {
  const _VoiceActionCircle({
    required this.icon,
    required this.onTap,
    this.isLoading = false,
  });

  final IconData icon;
  final VoidCallback? onTap;
  final bool isLoading;

  @override
  Widget build(BuildContext context) {
    return InkWell(
      onTap: onTap,
      customBorder: const CircleBorder(),
      child: Container(
        width: 34,
        height: 34,
        decoration: const BoxDecoration(
          color: Color(0x40FFFFFF),
          shape: BoxShape.circle,
        ),
        alignment: Alignment.center,
        child: isLoading
            ? const SizedBox(
                width: 16,
                height: 16,
                child: CircularProgressIndicator(
                  strokeWidth: 2,
                  color: Colors.white,
                ),
              )
            : Icon(icon, color: Colors.white, size: 20),
      ),
    );
  }
}

class _VoiceWaveform extends StatelessWidget {
  const _VoiceWaveform({required this.progress, required this.isRecording});

  final double progress;
  final bool isRecording;

  static const List<double> _basePattern = [
    0.16,
    0.42,
    0.28,
    0.72,
    0.34,
    0.58,
    0.22,
    0.48,
    0.31,
    0.66,
    0.26,
    0.52,
    0.19,
    0.61,
    0.35,
    0.73,
  ];

  @override
  Widget build(BuildContext context) {
    final safeProgress = progress.clamp(0, 1).toDouble();

    return LayoutBuilder(
      builder: (context, constraints) {
        final barCount = ((constraints.maxWidth / 5).floor()).clamp(14, 40);
        final activeBars = (barCount * safeProgress).floor();
        return Row(
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          crossAxisAlignment: CrossAxisAlignment.center,
          children: List.generate(barCount, (index) {
            final patternValue = _basePattern[index % _basePattern.length];
            final height = 6 + (patternValue * 14);
            final isActive = isRecording || index < activeBars;
            return Container(
              width: 2.4,
              height: height,
              decoration: BoxDecoration(
                color: isActive ? Colors.white : Colors.white.withOpacity(0.34),
                borderRadius: BorderRadius.circular(2),
              ),
            );
          }),
        );
      },
    );
  }
}

class _ChatHeader extends StatelessWidget {
  const _ChatHeader({
    required this.contactName,
    required this.avatar,
    required this.capabilities,
    required this.onBack,
    required this.canOpenContact,
    required this.onOpenContact,
    required this.onMenuAction,
  });

  final String contactName;
  final String avatar;
  final ConversationCapabilities capabilities;
  final VoidCallback onBack;
  final bool canOpenContact;
  final VoidCallback onOpenContact;
  final ValueChanged<_ChatMenuAction> onMenuAction;

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: const BoxDecoration(
        color: Colors.white,
        border: Border(bottom: BorderSide(color: Color(0xFFE3E7EE))),
      ),
      padding: const EdgeInsets.symmetric(horizontal: 4, vertical: 6),
      child: Row(
        children: [
          IconButton(
            onPressed: onBack,
            icon: const Icon(
              Icons.arrow_back,
              color: Color(0xFF22262F),
              size: 22,
            ),
          ),
          Padding(
            padding: const EdgeInsets.all(2),
            child: LeroAvatar(
              key: const Key('chat_header_avatar'),
              text: avatar,
              size: 42,
              enablePreview: true,
              previewTitle: contactName,
            ),
          ),
          const SizedBox(width: 8),
          Expanded(
            child: Material(
              color: Colors.transparent,
              child: InkWell(
                key: const Key('chat_header_contact_name'),
                onTap: canOpenContact ? onOpenContact : null,
                borderRadius: BorderRadius.circular(10),
                child: Padding(
                  padding: const EdgeInsets.symmetric(vertical: 4),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        contactName,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: const TextStyle(
                          fontSize: 18,
                          fontWeight: FontWeight.w700,
                          color: Color(0xFF1E222A),
                        ),
                      ),
                    ],
                  ),
                ),
              ),
            ),
          ),
          PopupMenuButton<_ChatMenuAction>(
            icon: const Icon(
              Icons.more_vert,
              size: 22,
              color: Color(0xFF1E222A),
            ),
            shape: RoundedRectangleBorder(
              borderRadius: BorderRadius.circular(12),
            ),
            onSelected: onMenuAction,
            itemBuilder: (context) {
              final items = <PopupMenuEntry<_ChatMenuAction>>[
                _chatMenuItem(
                  _ChatMenuAction.search,
                  Icons.search,
                  'Pesquisar mensagens',
                ),
              ];

              if (capabilities.canClose) {
                items.add(
                  _chatMenuItem(
                    _ChatMenuAction.close,
                    Icons.check_circle_outline,
                    'Finalizar atendimento',
                    iconColor: AppColors.success,
                  ),
                );
              }
              if (capabilities.canTransfer) {
                items.add(
                  _chatMenuItem(
                    _ChatMenuAction.transfer,
                    Icons.compare_arrows_rounded,
                    'Transferir atendimento',
                  ),
                );
              }
              if (capabilities.canClose || capabilities.canTransfer) {
                items.add(const PopupMenuDivider());
              }

              items.addAll(<PopupMenuEntry<_ChatMenuAction>>[
                _chatMenuItem(
                  _ChatMenuAction.media,
                  Icons.image_outlined,
                  'Midia, links e docs',
                ),
                _chatMenuItem(
                  _ChatMenuAction.favorites,
                  Icons.star_border_rounded,
                  'Ver mensagens favoritas',
                ),
                _chatMenuItem(
                  _ChatMenuAction.notes,
                  Icons.note_alt_outlined,
                  'Ver notas internas',
                  iconColor: Color(0xFF8B5CF6),
                ),
              ]);

              return items;
            },
          ),
        ],
      ),
    );
  }

  PopupMenuItem<_ChatMenuAction> _chatMenuItem(
    _ChatMenuAction value,
    IconData icon,
    String label, {
    Color iconColor = const Color(0xFF1F232B),
  }) {
    return PopupMenuItem<_ChatMenuAction>(
      value: value,
      height: 44,
      child: SizedBox(
        width: 260,
        child: Row(
          children: [
            Icon(icon, size: 22, color: iconColor),
            const SizedBox(width: 10),
            Expanded(
              child: Text(
                label,
                style: const TextStyle(
                  fontSize: 15.5,
                  color: Color(0xFF1F232B),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _ChatSelectionHeader extends StatelessWidget {
  const _ChatSelectionHeader({
    required this.count,
    required this.canReply,
    required this.canFavorite,
    required this.canDelete,
    required this.canCopy,
    required this.canForward,
    required this.onBack,
    this.onReply,
    this.onFavorite,
    this.onDelete,
    this.onCopy,
    this.onForward,
  });

  final int count;
  final bool canReply;
  final bool canFavorite;
  final bool canDelete;
  final bool canCopy;
  final bool canForward;
  final VoidCallback onBack;
  final VoidCallback? onReply;
  final VoidCallback? onFavorite;
  final VoidCallback? onDelete;
  final VoidCallback? onCopy;
  final VoidCallback? onForward;

  @override
  Widget build(BuildContext context) {
    return Container(
      key: const Key('chat_selection_header'),
      decoration: const BoxDecoration(
        color: Colors.white,
        border: Border(bottom: BorderSide(color: Color(0xFFE3E7EE))),
      ),
      padding: const EdgeInsets.symmetric(horizontal: 4, vertical: 6),
      child: Row(
        children: [
          IconButton(
            onPressed: onBack,
            icon: const Icon(
              Icons.arrow_back,
              color: Color(0xFF22262F),
              size: 22,
            ),
          ),
          SizedBox(
            width: 36,
            child: Text(
              '$count',
              key: const Key('chat_selection_count'),
              textAlign: TextAlign.center,
              style: const TextStyle(
                fontSize: 21,
                fontWeight: FontWeight.w500,
                color: Color(0xFF12161D),
              ),
            ),
          ),
          const Spacer(),
          if (canReply)
            IconButton(
              key: const Key('chat_selection_reply'),
              onPressed: onReply,
              icon: const Icon(Icons.reply_rounded),
              color: const Color(0xFF111827),
            ),
          if (canFavorite)
            IconButton(
              key: const Key('chat_selection_favorite'),
              onPressed: onFavorite,
              icon: const Icon(Icons.star_border_rounded),
              color: const Color(0xFF111827),
            ),
          if (canDelete)
            IconButton(
              key: const Key('chat_selection_delete'),
              onPressed: onDelete,
              icon: const Icon(Icons.delete_outline_rounded),
              color: const Color(0xFF111827),
            ),
          if (canCopy)
            IconButton(
              key: const Key('chat_selection_copy'),
              onPressed: onCopy,
              icon: const Icon(Icons.content_copy_outlined),
              color: const Color(0xFF111827),
            ),
          if (canForward)
            IconButton(
              key: const Key('chat_selection_forward'),
              onPressed: onForward,
              icon: const Icon(Icons.forward_rounded),
              color: const Color(0xFF111827),
            ),
        ],
      ),
    );
  }
}

class _ConnectionAvailabilityBanner extends StatelessWidget {
  const _ConnectionAvailabilityBanner({required this.message});

  final String message;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.fromLTRB(14, 12, 14, 12),
      decoration: const BoxDecoration(
        color: Color(0xFFFFF4ED),
        border: Border(
          top: BorderSide(color: Color(0xFFF3D5C7)),
          bottom: BorderSide(color: Color(0xFFF3D5C7)),
        ),
      ),
      child: Text(
        message,
        style: const TextStyle(
          color: Color(0xFF8A4B20),
          fontSize: 12.5,
          fontWeight: FontWeight.w600,
        ),
      ),
    );
  }
}

class _AgentTimelineBubble extends StatelessWidget {
  const _AgentTimelineBubble({
    required this.item,
    required this.isHighlighted,
    required this.isSelected,
    required this.onTap,
    required this.onLongPress,
    this.onToggleFavorite,
    this.reactionPicker,
  });

  final ChatMessageItem item;
  final bool isHighlighted;
  final bool isSelected;
  final VoidCallback onTap;
  final VoidCallback onLongPress;
  final VoidCallback? onToggleFavorite;
  final Widget? reactionPicker;

  @override
  Widget build(BuildContext context) {
    return _TimelineBubbleFrame(
      item: item,
      isAgentMessage: true,
      isHighlighted: isHighlighted,
      isSelected: isSelected,
      onTap: onTap,
      onLongPress: onLongPress,
      onToggleFavorite: onToggleFavorite,
      reactionPicker: reactionPicker,
    );
  }
}

class _SystemTimelineCard extends StatelessWidget {
  const _SystemTimelineCard({required this.message});

  final Message message;

  @override
  Widget build(BuildContext context) {
    final style = _SystemTimelineVisual.fromText(message.text);
    return Padding(
      padding: const EdgeInsets.fromLTRB(0, 4, 0, 10),
      child: Align(
        alignment: Alignment.center,
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 460),
          child: Container(
            padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 7),
            decoration: BoxDecoration(
              color: style.backgroundColor,
              borderRadius: BorderRadius.circular(10),
              border: Border.all(color: style.borderColor),
            ),
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                Icon(style.icon, color: style.iconColor, size: 15),
                const SizedBox(width: 6),
                Flexible(
                  child: Text(
                    message.text,
                    textAlign: TextAlign.center,
                    style: TextStyle(
                      color: style.textColor,
                      fontSize: 12,
                      fontWeight: FontWeight.w600,
                      height: 1.25,
                    ),
                  ),
                ),
                const SizedBox(width: 8),
                Text(
                  DateTimeUtils.formatHourMinute(message.sentAt),
                  style: TextStyle(
                    color: style.textColor.withValues(alpha: 0.72),
                    fontSize: 11,
                    fontWeight: FontWeight.w600,
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _SystemTimelineVisual {
  const _SystemTimelineVisual({
    required this.backgroundColor,
    required this.borderColor,
    required this.textColor,
    required this.iconColor,
    required this.icon,
  });

  final Color backgroundColor;
  final Color borderColor;
  final Color textColor;
  final Color iconColor;
  final IconData icon;

  static _SystemTimelineVisual fromText(String rawText) {
    final normalized = rawText.toLowerCase();
    final isTransfer =
        normalized.contains('transfer') || normalized.contains('encaminh');
    final isClosed =
        normalized.contains('finaliz') ||
        normalized.contains('encerr') ||
        normalized.contains('conclu');

    if (isTransfer) {
      return const _SystemTimelineVisual(
        backgroundColor: Color(0x1A3B82F6),
        borderColor: Color(0x334285F4),
        textColor: Color(0xFF1D4ED8),
        iconColor: Color(0xFF2563EB),
        icon: Icons.swap_horiz_rounded,
      );
    }

    if (isClosed) {
      return const _SystemTimelineVisual(
        backgroundColor: Color(0x1A22C55E),
        borderColor: Color(0x3332C766),
        textColor: Color(0xFF15803D),
        iconColor: Color(0xFF16A34A),
        icon: Icons.check_circle_outline_rounded,
      );
    }

    return const _SystemTimelineVisual(
      backgroundColor: Color(0x1494A3B8),
      borderColor: Color(0x2694A3B8),
      textColor: Color(0xFF475569),
      iconColor: Color(0xFF64748B),
      icon: Icons.info_outline_rounded,
    );
  }
}

class _ContactTimelineBubble extends StatelessWidget {
  const _ContactTimelineBubble({
    required this.item,
    required this.isHighlighted,
    required this.isSelected,
    required this.onTap,
    required this.onLongPress,
    this.onToggleFavorite,
    this.reactionPicker,
  });

  final ChatMessageItem item;
  final bool isHighlighted;
  final bool isSelected;
  final VoidCallback onTap;
  final VoidCallback onLongPress;
  final VoidCallback? onToggleFavorite;
  final Widget? reactionPicker;

  @override
  Widget build(BuildContext context) {
    return _TimelineBubbleFrame(
      item: item,
      isAgentMessage: false,
      isHighlighted: isHighlighted,
      isSelected: isSelected,
      onTap: onTap,
      onLongPress: onLongPress,
      onToggleFavorite: onToggleFavorite,
      reactionPicker: reactionPicker,
    );
  }
}

class _TimelineBubbleFrame extends StatelessWidget {
  const _TimelineBubbleFrame({
    required this.item,
    required this.isAgentMessage,
    required this.isHighlighted,
    required this.isSelected,
    required this.onTap,
    required this.onLongPress,
    this.onToggleFavorite,
    this.reactionPicker,
  });

  final ChatMessageItem item;
  final bool isAgentMessage;
  final bool isHighlighted;
  final bool isSelected;
  final VoidCallback onTap;
  final VoidCallback onLongPress;
  final VoidCallback? onToggleFavorite;
  final Widget? reactionPicker;

  @override
  Widget build(BuildContext context) {
    final message = item.message;
    final maxWidth = MediaQuery.of(context).size.width * 0.78;
    final hasAuthor = !item.isDeleted && message.authorName.trim().isNotEmpty;
    final replyPayload = item.isDeleted
        ? null
        : _ReplyPayload.tryParse(message.text);
    final bodyText = item.isDeleted
        ? (isAgentMessage
              ? 'Voce apagou esta mensagem'
              : 'Esta mensagem foi apagada')
        : (replyPayload?.body ?? message.text);
    final hasText = bodyText.trim().isNotEmpty;
    final showFooterFavorite = onToggleFavorite != null && !item.isDeleted;
    final reaction = item.primaryReaction;
    final baseBubbleColor = item.isDeleted
        ? (isAgentMessage ? const Color(0xFFFFE7DF) : const Color(0xFFF0F1F4))
        : (isAgentMessage ? AppColors.primary : const Color(0xFFE6E8EE));
    final baseTextColor = item.isDeleted
        ? const Color(0xFF6B7280)
        : (isAgentMessage ? Colors.white : const Color(0xFF1F232B));
    final highlightBorderColor = isSelected
        ? const Color(0xFF25D366)
        : (isAgentMessage ? const Color(0xFFFDE68A) : const Color(0xFFF59E0B));
    final footerTextColor = isAgentMessage
        ? Colors.white.withValues(alpha: item.isDeleted ? 0.72 : 0.92)
        : const Color(0xFF5F6776);
    final bubbleRadius = isAgentMessage
        ? const BorderRadius.only(
            topLeft: Radius.circular(16),
            topRight: Radius.circular(16),
            bottomLeft: Radius.circular(16),
            bottomRight: Radius.circular(4),
          )
        : const BorderRadius.only(
            topLeft: Radius.circular(16),
            topRight: Radius.circular(16),
            bottomLeft: Radius.circular(4),
            bottomRight: Radius.circular(16),
          );

    return Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: Align(
        alignment: isAgentMessage
            ? Alignment.centerRight
            : Alignment.centerLeft,
        child: Column(
          crossAxisAlignment: isAgentMessage
              ? CrossAxisAlignment.end
              : CrossAxisAlignment.start,
          children: [
            if (reactionPicker != null) ...[
              reactionPicker!,
              const SizedBox(height: 6),
            ],
            GestureDetector(
              onTap: onTap,
              onLongPress: onLongPress,
              child: ConstrainedBox(
                constraints: BoxConstraints(maxWidth: maxWidth),
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    AnimatedContainer(
                      duration: const Duration(milliseconds: 180),
                      padding: const EdgeInsets.all(2),
                      decoration: BoxDecoration(
                        color: isSelected
                            ? const Color(0x1625D366)
                            : Colors.transparent,
                        borderRadius: BorderRadius.circular(20),
                      ),
                      child: DecoratedBox(
                        decoration: BoxDecoration(
                          color: baseBubbleColor,
                          borderRadius: bubbleRadius,
                          border: (isHighlighted || isSelected)
                              ? Border.all(
                                  color: highlightBorderColor,
                                  width: isSelected ? 1.8 : 2,
                                )
                              : null,
                        ),
                        child: Padding(
                          padding: const EdgeInsets.fromLTRB(12, 8, 12, 6),
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              if (hasAuthor) ...[
                                Text(
                                  '${message.authorName}:',
                                  style: TextStyle(
                                    color: isAgentMessage
                                        ? Colors.white
                                        : const Color(0xFF2A2F39),
                                    fontSize: 13,
                                    fontWeight: FontWeight.w700,
                                  ),
                                ),
                                const SizedBox(height: 2),
                              ],
                              if (replyPayload != null) ...[
                                _ReplySnippet(
                                  author: replyPayload.author,
                                  preview: replyPayload.preview,
                                  isAgentMessage: isAgentMessage,
                                ),
                                const SizedBox(height: 6),
                              ],
                              if (hasText)
                                Text(
                                  bodyText,
                                  style: TextStyle(
                                    color: baseTextColor,
                                    height: 1.35,
                                    fontSize: 16,
                                    fontStyle: item.isDeleted
                                        ? FontStyle.italic
                                        : FontStyle.normal,
                                  ),
                                ),
                              if (!item.isDeleted &&
                                  message.attachments.isNotEmpty) ...[
                                if (hasText) const SizedBox(height: 8),
                                _MessageAttachmentPreview(
                                  attachments: message.attachments,
                                  isAgentMessage: isAgentMessage,
                                ),
                              ],
                              const SizedBox(height: 6),
                              Row(
                                mainAxisAlignment: MainAxisAlignment.end,
                                mainAxisSize: MainAxisSize.min,
                                children: [
                                  if (showFooterFavorite) ...[
                                    GestureDetector(
                                      onTap: onToggleFavorite,
                                      child: Icon(
                                        item.isFavorite
                                            ? Icons.star_rounded
                                            : Icons.star_border_rounded,
                                        size: 16,
                                        color: isAgentMessage
                                            ? Colors.white.withValues(
                                                alpha: 0.95,
                                              )
                                            : (item.isFavorite
                                                  ? const Color(0xFFF59E0B)
                                                  : const Color(0xFF5F6776)),
                                      ),
                                    ),
                                    const SizedBox(width: 4),
                                  ],
                                  Text(
                                    DateTimeUtils.formatHourMinute(
                                      message.sentAt,
                                    ),
                                    style: TextStyle(
                                      color: footerTextColor,
                                      fontSize: 12,
                                    ),
                                  ),
                                  if (isAgentMessage) ...[
                                    const SizedBox(width: 3),
                                    Icon(
                                      Icons.done_all,
                                      size: 15,
                                      color: footerTextColor,
                                    ),
                                  ],
                                ],
                              ),
                            ],
                          ),
                        ),
                      ),
                    ),
                    if (reaction != null)
                      Padding(
                        padding: const EdgeInsets.only(left: 12, top: 2),
                        child: _MessageReactionChip(emoji: reaction.emoji),
                      ),
                  ],
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _MessageReactionPicker extends StatelessWidget {
  const _MessageReactionPicker({
    required this.onEmojiSelected,
    required this.onMore,
  });

  final ValueChanged<String> onEmojiSelected;
  final VoidCallback onMore;

  @override
  Widget build(BuildContext context) {
    return Container(
      key: const Key('chat_reaction_picker'),
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 6),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(26),
        boxShadow: const [
          BoxShadow(
            color: Color(0x16000000),
            blurRadius: 14,
            offset: Offset(0, 6),
          ),
        ],
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          for (final emoji in _ChatPageState._quickReactionEmojis)
            _ReactionPickerButton(
              emoji: emoji,
              onTap: () => onEmojiSelected(emoji),
            ),
          Container(
            width: 36,
            height: 36,
            margin: const EdgeInsets.only(left: 2),
            decoration: const BoxDecoration(
              color: Color(0xFFF1F3F6),
              shape: BoxShape.circle,
            ),
            child: IconButton(
              key: const Key('chat_reaction_more'),
              onPressed: onMore,
              padding: EdgeInsets.zero,
              splashRadius: 18,
              icon: const Icon(
                Icons.add_rounded,
                size: 22,
                color: Color(0xFF6B7280),
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _ReactionPickerButton extends StatelessWidget {
  const _ReactionPickerButton({required this.emoji, required this.onTap});

  final String emoji;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.circular(18),
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 4, vertical: 2),
        child: Text(emoji, style: const TextStyle(fontSize: 28)),
      ),
    );
  }
}

class _MessageReactionChip extends StatelessWidget {
  const _MessageReactionChip({required this.emoji});

  final String emoji;

  @override
  Widget build(BuildContext context) {
    return Container(
      key: const Key('chat_message_reaction_chip'),
      padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 2),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: const Color(0xFFDCE2EA)),
      ),
      child: Text(emoji, style: const TextStyle(fontSize: 16)),
    );
  }
}

class _MessageAttachmentPreview extends StatelessWidget {
  const _MessageAttachmentPreview({
    required this.attachments,
    required this.isAgentMessage,
  });

  final List<Attachment> attachments;
  final bool isAgentMessage;

  @override
  Widget build(BuildContext context) {
    final attachment = attachments.first;
    final foreground = isAgentMessage ? Colors.white : const Color(0xFF2A2F39);
    final background = isAgentMessage
        ? const Color(0x1FFFFFFF)
        : const Color(0xFFD8DCE5);
    final isDocumentLike =
        attachment.type == AttachmentType.document ||
        attachment.type == AttachmentType.other;

    if (attachment.type == AttachmentType.audio) {
      return _ChatAudioAttachmentPlayer(
        attachment: attachment,
        isAgentMessage: isAgentMessage,
      );
    }

    if (attachment.type == AttachmentType.image) {
      return _ChatImageAttachmentPreview(
        attachment: attachment,
        isAgentMessage: isAgentMessage,
      );
    }

    if (attachment.type == AttachmentType.video) {
      return _ChatVideoAttachmentPreview(
        attachment: attachment,
        isAgentMessage: isAgentMessage,
      );
    }

    if (attachment.type == AttachmentType.location) {
      return _ChatLocationAttachmentPreview(
        attachment: attachment,
        isAgentMessage: isAgentMessage,
      );
    }

    final content = Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
      decoration: BoxDecoration(
        color: background,
        borderRadius: BorderRadius.circular(12),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(_iconForType(attachment.type), size: 18, color: foreground),
          const SizedBox(width: 6),
          ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 190),
            child: Text(
              attachment.fileName,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: TextStyle(
                color: foreground,
                fontSize: 14,
                fontWeight: FontWeight.w600,
              ),
            ),
          ),
          if (isDocumentLike) ...[
            const SizedBox(width: 6),
            Icon(
              Icons.open_in_new_rounded,
              size: 16,
              color: foreground.withOpacity(0.9),
            ),
          ],
        ],
      ),
    );

    if (!isDocumentLike) {
      return content;
    }

    return InkWell(
      onTap: () => unawaited(_openDocument(context, attachment)),
      borderRadius: BorderRadius.circular(12),
      child: content,
    );
  }

  IconData _iconForType(AttachmentType type) {
    switch (type) {
      case AttachmentType.image:
        return Icons.image_outlined;
      case AttachmentType.video:
        return Icons.videocam_outlined;
      case AttachmentType.document:
        return Icons.insert_drive_file_outlined;
      case AttachmentType.audio:
        return Icons.graphic_eq_rounded;
      case AttachmentType.location:
        return Icons.location_on_outlined;
      case AttachmentType.other:
        return Icons.attach_file_rounded;
    }
  }

  Future<void> _openDocument(
    BuildContext context,
    Attachment attachment,
  ) async {
    final source = attachment.url.trim();
    if (source.isEmpty || source.startsWith('mock://')) {
      _showAttachmentFeedback(context, 'Documento indisponivel para abrir.');
      return;
    }

    if (source.startsWith('http://') || source.startsWith('https://')) {
      _showAttachmentFeedback(
        context,
        'Abertura de documento remoto ainda nao suportada.',
      );
      return;
    }

    final file = File(source);
    if (!file.existsSync()) {
      _showAttachmentFeedback(context, 'Arquivo de documento nao encontrado.');
      return;
    }

    try {
      final result = await OpenFilex.open(source);
      if (result.type != ResultType.done) {
        _showAttachmentFeedback(context, 'Nao foi possivel abrir o documento.');
      }
    } catch (_) {
      _showAttachmentFeedback(context, 'Falha ao abrir o documento.');
    }
  }

  void _showAttachmentFeedback(BuildContext context, String message) {
    final messenger = ScaffoldMessenger.maybeOf(context);
    if (messenger == null) return;
    messenger.hideCurrentSnackBar();
    messenger.showSnackBar(SnackBar(content: Text(message)));
  }
}

class _ChatLocationAttachmentPreview extends StatelessWidget {
  const _ChatLocationAttachmentPreview({
    required this.attachment,
    required this.isAgentMessage,
  });

  final Attachment attachment;
  final bool isAgentMessage;

  Uri? _mapUri() {
    final source = attachment.url.trim();
    if (source.isEmpty || source.startsWith('mock://')) {
      return null;
    }
    return Uri.tryParse(source);
  }

  String _coordinatesLabel(Uri? uri) {
    if (uri == null) {
      return 'Toque para abrir no mapa';
    }

    final raw = (uri.queryParameters['q'] ?? uri.queryParameters['query'] ?? '')
        .trim();
    if (raw.isEmpty) {
      return 'Toque para abrir no mapa';
    }

    final parts = raw.split(',');
    if (parts.length < 2) {
      return raw;
    }

    final lat = double.tryParse(parts[0].trim());
    final lng = double.tryParse(parts[1].trim());
    if (lat == null || lng == null) {
      return raw;
    }
    return '${lat.toStringAsFixed(5)}, ${lng.toStringAsFixed(5)}';
  }

  Future<void> _openMap(BuildContext context) async {
    final uri = _mapUri();
    if (uri == null) {
      _showFeedback(context, 'Localizacao indisponivel para abrir.');
      return;
    }

    try {
      final launched = await launchUrl(
        uri,
        mode: LaunchMode.externalApplication,
      );
      if (!launched) {
        _showFeedback(context, 'Nao foi possivel abrir o mapa.');
      }
    } catch (_) {
      _showFeedback(context, 'Falha ao abrir a localizacao.');
    }
  }

  void _showFeedback(BuildContext context, String message) {
    final messenger = ScaffoldMessenger.maybeOf(context);
    if (messenger == null) return;
    messenger.hideCurrentSnackBar();
    messenger.showSnackBar(SnackBar(content: Text(message)));
  }

  @override
  Widget build(BuildContext context) {
    final foreground = isAgentMessage ? Colors.white : const Color(0xFF2A2F39);
    final background = isAgentMessage
        ? const Color(0x1FFFFFFF)
        : const Color(0xFFD8DCE5);
    final iconBg = isAgentMessage
        ? const Color(0x33FFFFFF)
        : const Color(0xFFC6CCD8);
    final title = attachment.fileName.trim().isEmpty
        ? 'Localizacao'
        : attachment.fileName.trim();
    final uri = _mapUri();

    return InkWell(
      onTap: () => unawaited(_openMap(context)),
      borderRadius: BorderRadius.circular(12),
      child: Container(
        constraints: const BoxConstraints(minWidth: 210, maxWidth: 260),
        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 10),
        decoration: BoxDecoration(
          color: background,
          borderRadius: BorderRadius.circular(12),
        ),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Container(
              width: 34,
              height: 34,
              decoration: BoxDecoration(color: iconBg, shape: BoxShape.circle),
              alignment: Alignment.center,
              child: Icon(
                Icons.location_on_rounded,
                color: foreground,
                size: 20,
              ),
            ),
            const SizedBox(width: 8),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    title,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: TextStyle(
                      color: foreground,
                      fontSize: 14,
                      fontWeight: FontWeight.w700,
                    ),
                  ),
                  const SizedBox(height: 2),
                  Text(
                    _coordinatesLabel(uri),
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: TextStyle(
                      color: foreground.withOpacity(0.88),
                      fontSize: 12.5,
                      fontWeight: FontWeight.w500,
                    ),
                  ),
                  const SizedBox(height: 2),
                  Text(
                    'Abrir no mapa',
                    style: TextStyle(
                      color: foreground.withOpacity(0.95),
                      fontSize: 12,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                ],
              ),
            ),
            Icon(
              Icons.open_in_new_rounded,
              size: 16,
              color: foreground.withOpacity(0.9),
            ),
          ],
        ),
      ),
    );
  }
}

class _ChatImageAttachmentPreview extends StatelessWidget {
  const _ChatImageAttachmentPreview({
    required this.attachment,
    required this.isAgentMessage,
  });

  final Attachment attachment;
  final bool isAgentMessage;

  bool get _isNetworkImage =>
      _isNetworkAttachmentSource(attachment.url);

  bool get _isLocalImage =>
      _isLocalAttachmentSource(attachment.url);

  @override
  Widget build(BuildContext context) {
    final bgColor = isAgentMessage
        ? const Color(0x1FFFFFFF)
        : const Color(0xFFD8DCE5);

    return GestureDetector(
      onTap: () => _openImagePreview(context),
      child: ClipRRect(
        borderRadius: BorderRadius.circular(12),
        child: Container(
          width: 200,
          height: 200,
          color: bgColor,
          child: _buildImage(
            fit: BoxFit.cover,
            fallbackColor: isAgentMessage
                ? Colors.white
                : const Color(0xFF2A2F39),
          ),
        ),
      ),
    );
  }

  Widget _buildImage({required BoxFit fit, required Color fallbackColor}) {
    if (_isNetworkImage) {
      return Image.network(
        attachment.url,
        fit: fit,
        errorBuilder: (_, __, ___) => _imageFallback(fallbackColor),
      );
    }

    if (_isLocalImage) {
      return Image.file(
        File(attachment.url),
        fit: fit,
        errorBuilder: (_, __, ___) => _imageFallback(fallbackColor),
      );
    }

    return _imageFallback(fallbackColor);
  }

  Widget _imageFallback(Color color) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 10),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(Icons.image_not_supported_outlined, color: color, size: 28),
            const SizedBox(height: 6),
            Text(
              attachment.fileName,
              maxLines: 2,
              overflow: TextOverflow.ellipsis,
              textAlign: TextAlign.center,
              style: TextStyle(
                color: color,
                fontSize: 12,
                fontWeight: FontWeight.w600,
              ),
            ),
          ],
        ),
      ),
    );
  }

  void _openImagePreview(BuildContext context) {
    Navigator.of(context).push(
      MaterialPageRoute(
        builder: (_) => _FullScreenImageViewer(attachment: attachment),
      ),
    );
  }
}

class _ChatVideoAttachmentPreview extends StatefulWidget {
  const _ChatVideoAttachmentPreview({
    required this.attachment,
    required this.isAgentMessage,
  });

  final Attachment attachment;
  final bool isAgentMessage;

  @override
  State<_ChatVideoAttachmentPreview> createState() =>
      _ChatVideoAttachmentPreviewState();
}

class _ChatVideoAttachmentPreviewState
    extends State<_ChatVideoAttachmentPreview> {
  VideoPlayerController? _controller;
  bool _isPreparing = true;
  bool _hasLoadError = false;
  int _lastPositionBucket = -1;
  bool _lastIsPlaying = false;

  bool get _isNetworkSource =>
      _isNetworkAttachmentSource(widget.attachment.url);

  bool get _isLocalSource =>
      _isLocalAttachmentSource(widget.attachment.url);

  @override
  void initState() {
    super.initState();
    unawaited(_prepareVideo());
  }

  @override
  void didUpdateWidget(covariant _ChatVideoAttachmentPreview oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.attachment.url != widget.attachment.url) {
      unawaited(_prepareVideo());
    }
  }

  @override
  void dispose() {
    final current = _controller;
    _controller = null;
    if (current != null) {
      current.removeListener(_onVideoControllerTick);
      unawaited(current.dispose());
    }
    super.dispose();
  }

  Future<void> _prepareVideo() async {
    if (mounted) {
      setState(() {
        _isPreparing = true;
        _hasLoadError = false;
      });
    }

    final source = widget.attachment.url.trim();
    if (source.isEmpty || (!_isNetworkSource && !_isLocalSource)) {
      if (!mounted) return;
      setState(() {
        _isPreparing = false;
        _hasLoadError = true;
      });
      return;
    }

    final old = _controller;
    VideoPlayerController controller;
    if (_isNetworkSource) {
      controller = VideoPlayerController.networkUrl(Uri.parse(source));
    } else {
      controller = VideoPlayerController.file(File(source));
    }

    _controller = controller;
    if (old != null) {
      old.removeListener(_onVideoControllerTick);
      unawaited(old.dispose());
    }
    controller.addListener(_onVideoControllerTick);

    try {
      await controller.initialize();
      await controller.setLooping(false);
      _lastPositionBucket = 0;
      _lastIsPlaying = false;
      if (!mounted) return;
      setState(() {
        _isPreparing = false;
        _hasLoadError = false;
      });
    } catch (_) {
      if (!mounted) return;
      setState(() {
        _isPreparing = false;
        _hasLoadError = true;
      });
    }
  }

  void _onVideoControllerTick() {
    final controller = _controller;
    if (!mounted || controller == null || !controller.value.isInitialized) {
      return;
    }
    final bucket = controller.value.position.inMilliseconds ~/ 250;
    final isPlaying = controller.value.isPlaying;
    if (bucket == _lastPositionBucket && isPlaying == _lastIsPlaying) return;
    _lastPositionBucket = bucket;
    _lastIsPlaying = isPlaying;
    setState(() {});
  }

  Future<void> _togglePlayback() async {
    final controller = _controller;
    if (controller == null || !controller.value.isInitialized) return;
    if (controller.value.isPlaying) {
      await controller.pause();
      if (!mounted) return;
      setState(() {});
      return;
    }
    if (controller.value.position >= controller.value.duration) {
      await controller.seekTo(Duration.zero);
    }
    await controller.play();
    if (!mounted) return;
    setState(() {});
  }

  Future<void> _seekTo(double value) async {
    final controller = _controller;
    if (controller == null || !controller.value.isInitialized) return;
    await controller.seekTo(Duration(milliseconds: value.round()));
    if (!mounted) return;
    setState(() {});
  }

  Future<void> _openVideoPreview() async {
    final controller = _controller;
    if (controller != null && controller.value.isPlaying) {
      await controller.pause();
    }
    if (!mounted) return;
    await Navigator.of(context).push(
      MaterialPageRoute(
        builder: (_) => _FullScreenVideoViewer(attachment: widget.attachment),
      ),
    );
  }

  String _formatDuration(Duration value) {
    return _formatClockDuration(value);
  }

  @override
  Widget build(BuildContext context) {
    final foreground = widget.isAgentMessage
        ? Colors.white
        : const Color(0xFF1F2937);
    final background = widget.isAgentMessage
        ? const Color(0x1FFFFFFF)
        : const Color(0xFFD8DCE5);
    final controller = _controller;
    final duration = controller?.value.duration ?? Duration.zero;
    final position = controller?.value.position ?? Duration.zero;
    final durationMs = duration.inMilliseconds <= 0
        ? 1
        : duration.inMilliseconds;
    final positionMs = position.inMilliseconds.clamp(0, durationMs);

    return Container(
      width: 220,
      decoration: BoxDecoration(
        color: background,
        borderRadius: BorderRadius.circular(12),
      ),
      padding: const EdgeInsets.all(8),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          ClipRRect(
            borderRadius: BorderRadius.circular(10),
            child: SizedBox(
              width: double.infinity,
              height: 124,
              child: _hasLoadError
                  ? _VideoFallback(
                      color: foreground,
                      fileName: widget.attachment.fileName,
                    )
                  : _isPreparing ||
                        controller == null ||
                        !controller.value.isInitialized
                  ? DecoratedBox(
                      decoration: const BoxDecoration(color: Color(0xFF111827)),
                      child: const Center(
                        child: SizedBox(
                          width: 22,
                          height: 22,
                          child: CircularProgressIndicator(strokeWidth: 2),
                        ),
                      ),
                    )
                  : GestureDetector(
                      onTap: () => unawaited(_togglePlayback()),
                      child: Stack(
                        fit: StackFit.expand,
                        children: [
                          AnimatedBuilder(
                            animation: controller,
                            builder: (_, __) {
                              return FittedBox(
                                fit: BoxFit.cover,
                                child: SizedBox(
                                  width: controller.value.size.width,
                                  height: controller.value.size.height,
                                  child: VideoPlayer(controller),
                                ),
                              );
                            },
                          ),
                          Container(color: Colors.black.withOpacity(0.16)),
                          Center(
                            child: AnimatedBuilder(
                              animation: controller,
                              builder: (_, __) {
                                return Icon(
                                  controller.value.isPlaying
                                      ? Icons.pause_circle_filled_rounded
                                      : Icons.play_circle_fill_rounded,
                                  size: 48,
                                  color: Colors.white.withOpacity(0.95),
                                );
                              },
                            ),
                          ),
                          Positioned(
                            top: 6,
                            right: 6,
                            child: GestureDetector(
                              onTap: () => unawaited(_openVideoPreview()),
                              child: Container(
                                decoration: BoxDecoration(
                                  color: Colors.black.withOpacity(0.4),
                                  shape: BoxShape.circle,
                                ),
                                padding: const EdgeInsets.all(5),
                                child: const Icon(
                                  Icons.fullscreen_rounded,
                                  color: Colors.white,
                                  size: 18,
                                ),
                              ),
                            ),
                          ),
                        ],
                      ),
                    ),
            ),
          ),
          const SizedBox(height: 8),
          Text(
            widget.attachment.fileName,
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: TextStyle(
              color: foreground,
              fontSize: 12,
              fontWeight: FontWeight.w600,
            ),
          ),
          const SizedBox(height: 4),
          Row(
            children: [
              Icon(
                Icons.videocam_rounded,
                color: foreground.withOpacity(0.9),
                size: 15,
              ),
              const SizedBox(width: 5),
              Expanded(
                child: SliderTheme(
                  data: SliderTheme.of(context).copyWith(
                    trackHeight: 2.8,
                    thumbShape: const RoundSliderThumbShape(
                      enabledThumbRadius: 5,
                    ),
                    overlayShape: const RoundSliderOverlayShape(
                      overlayRadius: 9,
                    ),
                    activeTrackColor: foreground,
                    inactiveTrackColor: foreground.withOpacity(0.35),
                    thumbColor: foreground,
                    overlayColor: foreground.withOpacity(0.18),
                  ),
                  child: Slider(
                    value: positionMs.toDouble(),
                    max: durationMs.toDouble(),
                    onChanged:
                        _hasLoadError ||
                            _isPreparing ||
                            controller == null ||
                            !controller.value.isInitialized
                        ? null
                        : (value) {
                            unawaited(_seekTo(value));
                          },
                  ),
                ),
              ),
              Text(
                controller != null && controller.value.isInitialized
                    ? '${_formatDuration(position)} / ${_formatDuration(duration)}'
                    : '--:-- / --:--',
                style: TextStyle(
                  color: foreground.withOpacity(0.9),
                  fontSize: 11,
                  fontWeight: FontWeight.w600,
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }
}

class _VideoFallback extends StatelessWidget {
  const _VideoFallback({required this.color, required this.fileName});

  final Color color;
  final String fileName;

  @override
  Widget build(BuildContext context) {
    return DecoratedBox(
      decoration: const BoxDecoration(color: Color(0xFF111827)),
      child: Center(
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 10),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(Icons.videocam_off_rounded, color: color, size: 28),
              const SizedBox(height: 8),
              Text(
                fileName,
                maxLines: 2,
                overflow: TextOverflow.ellipsis,
                textAlign: TextAlign.center,
                style: TextStyle(
                  color: color,
                  fontSize: 11,
                  fontWeight: FontWeight.w600,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _FullScreenImageViewer extends StatelessWidget {
  const _FullScreenImageViewer({required this.attachment});

  final Attachment attachment;

  bool get _isNetworkImage =>
      _isNetworkAttachmentSource(attachment.url);

  bool get _isLocalImage =>
      _isLocalAttachmentSource(attachment.url);

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Colors.black,
      body: SafeArea(
        child: Stack(
          children: [
            Positioned.fill(
              child: InteractiveViewer(
                minScale: 0.8,
                maxScale: 4,
                child: Center(child: _buildImage()),
              ),
            ),
            Positioned(
              top: 8,
              right: 8,
              child: IconButton(
                onPressed: () => Navigator.of(context).pop(),
                icon: const Icon(
                  Icons.close_rounded,
                  color: Colors.white,
                  size: 30,
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildImage() {
    if (_isNetworkImage) {
      return Image.network(
        attachment.url,
        fit: BoxFit.contain,
        errorBuilder: (_, __, ___) => _fallback(),
      );
    }
    if (_isLocalImage) {
      return Image.file(
        File(attachment.url),
        fit: BoxFit.contain,
        errorBuilder: (_, __, ___) => _fallback(),
      );
    }
    return _fallback();
  }

  Widget _fallback() {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 20),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          const Icon(
            Icons.image_not_supported_outlined,
            color: Colors.white,
            size: 38,
          ),
          const SizedBox(height: 10),
          Text(
            attachment.fileName,
            maxLines: 2,
            overflow: TextOverflow.ellipsis,
            textAlign: TextAlign.center,
            style: const TextStyle(
              color: Colors.white,
              fontSize: 14,
              fontWeight: FontWeight.w600,
            ),
          ),
        ],
      ),
    );
  }
}

class _FullScreenVideoViewer extends StatefulWidget {
  const _FullScreenVideoViewer({required this.attachment});

  final Attachment attachment;

  @override
  State<_FullScreenVideoViewer> createState() => _FullScreenVideoViewerState();
}

class _FullScreenVideoViewerState extends State<_FullScreenVideoViewer> {
  VideoPlayerController? _controller;
  bool _isPreparing = true;
  bool _hasLoadError = false;
  int _lastPositionBucket = -1;
  bool _lastIsPlaying = false;

  bool get _isNetworkSource =>
      _isNetworkAttachmentSource(widget.attachment.url);

  bool get _isLocalSource =>
      _isLocalAttachmentSource(widget.attachment.url);

  @override
  void initState() {
    super.initState();
    unawaited(_prepareVideo());
  }

  @override
  void dispose() {
    final current = _controller;
    _controller = null;
    if (current != null) {
      current.removeListener(_onVideoControllerTick);
      unawaited(current.dispose());
    }
    super.dispose();
  }

  Future<void> _prepareVideo() async {
    setState(() {
      _isPreparing = true;
      _hasLoadError = false;
    });

    final source = widget.attachment.url.trim();
    if (source.isEmpty || (!_isNetworkSource && !_isLocalSource)) {
      if (!mounted) return;
      setState(() {
        _isPreparing = false;
        _hasLoadError = true;
      });
      return;
    }

    final old = _controller;
    VideoPlayerController controller;
    if (_isNetworkSource) {
      controller = VideoPlayerController.networkUrl(Uri.parse(source));
    } else {
      controller = VideoPlayerController.file(File(source));
    }
    _controller = controller;
    controller.addListener(_onVideoControllerTick);
    if (old != null) {
      old.removeListener(_onVideoControllerTick);
      unawaited(old.dispose());
    }

    try {
      await controller.initialize();
      await controller.setLooping(false);
      _lastPositionBucket = 0;
      _lastIsPlaying = false;
      if (!mounted) return;
      setState(() {
        _isPreparing = false;
        _hasLoadError = false;
      });
    } catch (_) {
      if (!mounted) return;
      setState(() {
        _isPreparing = false;
        _hasLoadError = true;
      });
    }
  }

  void _onVideoControllerTick() {
    final controller = _controller;
    if (!mounted || controller == null || !controller.value.isInitialized) {
      return;
    }
    final bucket = controller.value.position.inMilliseconds ~/ 250;
    final isPlaying = controller.value.isPlaying;
    if (bucket == _lastPositionBucket && isPlaying == _lastIsPlaying) return;
    _lastPositionBucket = bucket;
    _lastIsPlaying = isPlaying;
    setState(() {});
  }

  Future<void> _togglePlayback() async {
    final controller = _controller;
    if (controller == null || !controller.value.isInitialized) return;
    if (controller.value.isPlaying) {
      await controller.pause();
      return;
    }
    if (controller.value.position >= controller.value.duration) {
      await controller.seekTo(Duration.zero);
    }
    await controller.play();
  }

  Future<void> _seekTo(double value) async {
    final controller = _controller;
    if (controller == null || !controller.value.isInitialized) return;
    await controller.seekTo(Duration(milliseconds: value.round()));
  }

  String _formatDuration(Duration value) {
    return _formatClockDuration(value);
  }

  @override
  Widget build(BuildContext context) {
    final controller = _controller;
    final isReady =
        !_isPreparing &&
        !_hasLoadError &&
        controller != null &&
        controller.value.isInitialized;
    final readyController = isReady ? controller : null;
    final isPlaying = readyController?.value.isPlaying ?? false;
    final duration = readyController?.value.duration ?? Duration.zero;
    final position = readyController?.value.position ?? Duration.zero;
    final durationMs = duration.inMilliseconds <= 0
        ? 1
        : duration.inMilliseconds;
    final positionMs = position.inMilliseconds.clamp(0, durationMs);

    return Scaffold(
      backgroundColor: Colors.black,
      body: SafeArea(
        child: Column(
          children: [
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 4),
              child: Row(
                children: [
                  IconButton(
                    onPressed: () => Navigator.of(context).pop(),
                    icon: const Icon(
                      Icons.arrow_back_rounded,
                      color: Colors.white,
                    ),
                  ),
                  Expanded(
                    child: Text(
                      widget.attachment.fileName,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: const TextStyle(
                        color: Colors.white,
                        fontSize: 14,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                  ),
                ],
              ),
            ),
            Expanded(
              child: Center(
                child: _hasLoadError
                    ? const _VideoFallback(
                        color: Colors.white,
                        fileName: 'Video indisponivel',
                      )
                    : isReady
                    ? Builder(
                        builder: (context) {
                          final activeController = readyController!;
                          return GestureDetector(
                            onTap: () => unawaited(_togglePlayback()),
                            child: AspectRatio(
                              aspectRatio:
                                  activeController.value.aspectRatio == 0
                                  ? 16 / 9
                                  : activeController.value.aspectRatio,
                              child: Stack(
                                fit: StackFit.expand,
                                children: [
                                  VideoPlayer(activeController),
                                  Container(
                                    color: Colors.black.withOpacity(0.08),
                                  ),
                                  if (!isPlaying)
                                    Center(
                                      child: Icon(
                                        Icons.play_circle_fill_rounded,
                                        color: Colors.white.withOpacity(0.95),
                                        size: 68,
                                      ),
                                    ),
                                ],
                              ),
                            ),
                          );
                        },
                      )
                    : const SizedBox(
                        width: 34,
                        height: 34,
                        child: CircularProgressIndicator(
                          strokeWidth: 2.4,
                          color: Colors.white,
                        ),
                      ),
              ),
            ),
            Container(
              padding: const EdgeInsets.fromLTRB(10, 6, 10, 10),
              decoration: const BoxDecoration(color: Color(0xB3000000)),
              child: Row(
                children: [
                  IconButton(
                    onPressed: isReady
                        ? () => unawaited(_togglePlayback())
                        : null,
                    icon: Icon(
                      isPlaying
                          ? Icons.pause_rounded
                          : Icons.play_arrow_rounded,
                      color: Colors.white,
                      size: 30,
                    ),
                  ),
                  Text(
                    _formatDuration(position),
                    style: const TextStyle(
                      color: Colors.white,
                      fontSize: 12,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                  Expanded(
                    child: SliderTheme(
                      data: SliderTheme.of(context).copyWith(
                        trackHeight: 2.6,
                        thumbShape: const RoundSliderThumbShape(
                          enabledThumbRadius: 5,
                        ),
                        overlayShape: const RoundSliderOverlayShape(
                          overlayRadius: 10,
                        ),
                        activeTrackColor: Colors.white,
                        inactiveTrackColor: Colors.white38,
                        thumbColor: Colors.white,
                        overlayColor: Colors.white24,
                      ),
                      child: Slider(
                        value: positionMs.toDouble(),
                        max: durationMs.toDouble(),
                        onChanged: isReady
                            ? (value) {
                                unawaited(_seekTo(value));
                              }
                            : null,
                      ),
                    ),
                  ),
                  Text(
                    _formatDuration(duration),
                    style: const TextStyle(
                      color: Colors.white,
                      fontSize: 12,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _ChatAudioAttachmentPlayer extends StatefulWidget {
  const _ChatAudioAttachmentPlayer({
    required this.attachment,
    required this.isAgentMessage,
  });

  final Attachment attachment;
  final bool isAgentMessage;

  @override
  State<_ChatAudioAttachmentPlayer> createState() =>
      _ChatAudioAttachmentPlayerState();
}

class _ChatAudioAttachmentPlayerState
    extends State<_ChatAudioAttachmentPlayer> {
  final AudioPlayer _player = AudioPlayer();
  StreamSubscription<Duration?>? _durationSub;
  StreamSubscription<Duration>? _positionSub;
  StreamSubscription<PlayerState>? _stateSub;
  Duration _duration = Duration.zero;
  Duration _position = Duration.zero;
  bool _isPreparing = true;
  bool _hasLoadError = false;
  bool _isPlayerPlaying = false;
  ProcessingState _processingState = ProcessingState.idle;
  double _playbackSpeed = 1.0;

  @override
  void initState() {
    super.initState();
    _durationSub = _player.durationStream.listen((duration) {
      if (!mounted) return;
      setState(() {
        _duration = duration ?? Duration.zero;
      });
    });
    _positionSub = _player.positionStream.listen((position) {
      if (!mounted) return;
      setState(() {
        _position = position;
      });
    });
    _stateSub = _player.playerStateStream.listen((state) {
      if (!mounted) return;
      setState(() {
        _isPlayerPlaying = state.playing;
        _processingState = state.processingState;
      });
    });
    unawaited(_prepareAudio());
  }

  @override
  void didUpdateWidget(covariant _ChatAudioAttachmentPlayer oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.attachment.url != widget.attachment.url) {
      _position = Duration.zero;
      _duration = Duration.zero;
      unawaited(_prepareAudio());
    }
  }

  @override
  void dispose() {
    unawaited(_durationSub?.cancel());
    unawaited(_positionSub?.cancel());
    unawaited(_stateSub?.cancel());
    unawaited(_player.dispose());
    super.dispose();
  }

  Future<void> _prepareAudio() async {
    setState(() {
      _isPreparing = true;
      _hasLoadError = false;
      _isPlayerPlaying = false;
      _processingState = ProcessingState.loading;
    });

    final source = widget.attachment.url.trim();
    if (source.isEmpty || source.startsWith('mock://')) {
      if (!mounted) return;
      setState(() {
        _isPreparing = false;
        _hasLoadError = true;
        _processingState = ProcessingState.idle;
      });
      return;
    }

    try {
      await _player.stop();
      if (source.startsWith('http://') || source.startsWith('https://')) {
        await _player.setUrl(source);
      } else {
        await _player.setFilePath(source);
      }
      await _player.setSpeed(_playbackSpeed);
      if (!mounted) return;
      setState(() {
        _isPreparing = false;
        _processingState = ProcessingState.ready;
      });
    } catch (_) {
      if (!mounted) return;
      setState(() {
        _isPreparing = false;
        _hasLoadError = true;
        _processingState = ProcessingState.idle;
      });
    }
  }

  Future<void> _togglePlayback() async {
    if (_hasLoadError) {
      await _prepareAudio();
      if (_hasLoadError) return;
    }
    if (_isPlayerPlaying) {
      await _player.pause();
      return;
    }
    if (_duration > Duration.zero && _position >= _duration) {
      await _player.seek(Duration.zero);
    }
    await _player.play();
  }

  Future<void> _togglePlaybackSpeed() async {
    final nextSpeed = _playbackSpeed == 1.0
        ? 1.5
        : (_playbackSpeed == 1.5 ? 2.0 : 1.0);
    try {
      await _player.setSpeed(nextSpeed);
      if (!mounted) return;
      setState(() {
        _playbackSpeed = nextSpeed;
      });
    } catch (_) {
      // Ignore speed errors on unsupported platforms.
    }
  }

  String _formatDuration(Duration value) {
    return _formatClockDuration(value);
  }

  String _formatSpeed(double value) {
    if ((value - value.roundToDouble()).abs() < 0.001) {
      return '${value.toInt()}x';
    }
    return '${value.toStringAsFixed(1)}x';
  }

  @override
  Widget build(BuildContext context) {
    final foreground = Colors.white;
    final background = widget.isAgentMessage
        ? const Color(0xFFF97316)
        : const Color(0xFF6B7280);
    final iconBg = const Color(0x40FFFFFF);
    final isBuffering =
        _isPreparing ||
        _processingState == ProcessingState.loading ||
        _processingState == ProcessingState.buffering;
    final durationMs = _duration.inMilliseconds <= 0
        ? 1
        : _duration.inMilliseconds;
    final positionMs = _position.inMilliseconds.clamp(0, durationMs);
    final waveformProgress = (positionMs / durationMs).clamp(0, 1).toDouble();
    final timeLabel = _hasLoadError
        ? '--:--'
        : (_duration == Duration.zero
              ? _formatDuration(_position)
              : _formatDuration(_duration));

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 9),
      decoration: BoxDecoration(
        color: background,
        borderRadius: BorderRadius.circular(14),
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            'Mensagem de voz',
            style: TextStyle(
              color: foreground.withOpacity(0.98),
              fontSize: 14,
              fontWeight: FontWeight.w700,
            ),
          ),
          const SizedBox(height: 6),
          Row(
            children: [
              InkWell(
                onTap: _hasLoadError
                    ? null
                    : () => unawaited(_togglePlaybackSpeed()),
                borderRadius: BorderRadius.circular(13),
                child: Container(
                  padding: const EdgeInsets.symmetric(
                    horizontal: 9,
                    vertical: 4,
                  ),
                  decoration: BoxDecoration(
                    color: iconBg,
                    borderRadius: BorderRadius.circular(13),
                  ),
                  alignment: Alignment.center,
                  child: Text(
                    _formatSpeed(_playbackSpeed),
                    style: TextStyle(
                      color: foreground.withOpacity(_hasLoadError ? 0.7 : 1.0),
                      fontSize: 12,
                      fontWeight: FontWeight.w700,
                    ),
                  ),
                ),
              ),
              const SizedBox(width: 8),
              InkWell(
                onTap: isBuffering || _hasLoadError
                    ? null
                    : () => unawaited(_togglePlayback()),
                customBorder: const CircleBorder(),
                child: Container(
                  width: 34,
                  height: 34,
                  decoration: BoxDecoration(
                    color: iconBg,
                    shape: BoxShape.circle,
                  ),
                  alignment: Alignment.center,
                  child: isBuffering
                      ? SizedBox(
                          width: 16,
                          height: 16,
                          child: CircularProgressIndicator(
                            strokeWidth: 2,
                            color: foreground,
                          ),
                        )
                      : Icon(
                          _isPlayerPlaying
                              ? Icons.pause_rounded
                              : Icons.play_arrow_rounded,
                          color: foreground,
                          size: 20,
                        ),
                ),
              ),
              const SizedBox(width: 10),
              Expanded(
                child: _VoiceWaveform(
                  progress: _hasLoadError ? 0 : waveformProgress,
                  isRecording: false,
                ),
              ),
              const SizedBox(width: 8),
              Text(
                timeLabel,
                style: TextStyle(
                  color: foreground.withOpacity(0.95),
                  fontSize: 12,
                  fontWeight: FontWeight.w600,
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }
}

class _ReplyPayload {
  static const String _preferredPrefix = '[reply] ';
  static const List<String> _supportedPrefixes = [_preferredPrefix, '↩ '];

  const _ReplyPayload({
    required this.author,
    required this.preview,
    required this.body,
  });

  final String author;
  final String preview;
  final String body;

  static String get preferredPrefix => _preferredPrefix;

  static _ReplyPayload? tryParse(String rawText) {
    final splitIndex = rawText.indexOf('\n');
    if (splitIndex <= 0) return null;

    final firstLine = rawText.substring(0, splitIndex).trim();
    String? matchedPrefix;
    for (final prefix in _supportedPrefixes) {
      if (firstLine.startsWith(prefix)) {
        matchedPrefix = prefix;
        break;
      }
    }
    if (matchedPrefix == null) return null;

    final divider = firstLine.indexOf(': ', matchedPrefix.length);
    if (divider <= matchedPrefix.length) return null;

    final author = firstLine.substring(matchedPrefix.length, divider).trim();
    final preview = firstLine.substring(divider + 2).trim();
    final body = rawText.substring(splitIndex + 1).trim();
    if (author.isEmpty || preview.isEmpty || body.isEmpty) {
      return null;
    }

    return _ReplyPayload(author: author, preview: preview, body: body);
  }
}

class _ReplySnippet extends StatelessWidget {
  const _ReplySnippet({
    required this.author,
    required this.preview,
    required this.isAgentMessage,
  });

  final String author;
  final String preview;
  final bool isAgentMessage;

  @override
  Widget build(BuildContext context) {
    final accent = isAgentMessage
        ? const Color(0xFFFDE68A)
        : const Color(0xFFF59E0B);
    final background = isAgentMessage
        ? const Color(0x1FFFFFFF)
        : const Color(0xFFD8DCE5);
    final foreground = isAgentMessage ? Colors.white : const Color(0xFF2A2F39);

    return Container(
      width: double.infinity,
      padding: const EdgeInsets.fromLTRB(9, 6, 9, 6),
      decoration: BoxDecoration(
        color: background,
        borderRadius: BorderRadius.circular(10),
        border: Border(left: BorderSide(color: accent, width: 3)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            author,
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: TextStyle(
              color: foreground,
              fontSize: 12,
              fontWeight: FontWeight.w700,
            ),
          ),
          const SizedBox(height: 1),
          Text(
            preview,
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: TextStyle(
              color: foreground.withOpacity(0.9),
              fontSize: 12,
              fontWeight: FontWeight.w500,
            ),
          ),
        ],
      ),
    );
  }
}

class _ReplyComposerBar extends StatelessWidget {
  const _ReplyComposerBar({
    required this.author,
    required this.preview,
    required this.onCancel,
  });

  final String author;
  final String preview;
  final VoidCallback onCancel;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.fromLTRB(12, 8, 8, 8),
      decoration: const BoxDecoration(
        color: Color(0xFFF6F7FB),
        border: Border(
          top: BorderSide(color: Color(0xFFE4E7EF)),
          bottom: BorderSide(color: Color(0xFFE4E7EF)),
        ),
      ),
      child: Row(
        children: [
          Container(
            width: 4,
            height: 38,
            decoration: BoxDecoration(
              color: AppColors.primary,
              borderRadius: BorderRadius.circular(4),
            ),
          ),
          const SizedBox(width: 10),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  'Respondendo $author',
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: const TextStyle(
                    color: Color(0xFF1F2937),
                    fontSize: 13,
                    fontWeight: FontWeight.w700,
                  ),
                ),
                const SizedBox(height: 2),
                Text(
                  preview,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: const TextStyle(
                    color: Color(0xFF6B7280),
                    fontSize: 12.5,
                    fontWeight: FontWeight.w500,
                  ),
                ),
              ],
            ),
          ),
          IconButton(
            onPressed: onCancel,
            icon: const Icon(Icons.close_rounded, size: 20),
          ),
        ],
      ),
    );
  }
}

class _TodayBadge extends StatelessWidget {
  const _TodayBadge();

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
      decoration: BoxDecoration(
        color: const Color(0xFFF2F3F6),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: const Color(0xFFDEE2E9)),
      ),
      child: const Text(
        'Hoje',
        style: TextStyle(
          color: Color(0xFF6A7383),
          fontSize: 12,
          fontWeight: FontWeight.w600,
        ),
      ),
    );
  }
}

class _DownloadBar extends StatelessWidget {
  const _DownloadBar({required this.time, required this.onClose});

  final String time;
  final VoidCallback onClose;

  @override
  Widget build(BuildContext context) {
    return Material(
      color: const Color(0xFFE4E5EA),
      borderRadius: BorderRadius.circular(12),
      child: InkWell(
        onTap: onClose,
        borderRadius: BorderRadius.circular(12),
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
          child: Row(
            children: [
              const Icon(
                Icons.download,
                color: Color(0xFF242830),
                size: 26 / 1.2,
              ),
              const SizedBox(width: 12),
              const Expanded(
                child: Text(
                  'Baixar tudo',
                  style: TextStyle(
                    color: Color(0xFF242830),
                    fontSize: 18,
                    fontWeight: FontWeight.w500,
                  ),
                ),
              ),
              Text(
                time,
                style: const TextStyle(color: Color(0xFF5E6472), fontSize: 13),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _ScrollToBottomButton extends StatelessWidget {
  const _ScrollToBottomButton({required this.onTap});

  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return DecoratedBox(
      decoration: BoxDecoration(
        shape: BoxShape.circle,
        boxShadow: [
          BoxShadow(
            color: Colors.black.withOpacity(0.16),
            blurRadius: 8,
            offset: const Offset(0, 3),
          ),
        ],
      ),
      child: Material(
        color: const Color(0xFFE8E9EE),
        shape: const CircleBorder(),
        child: InkWell(
          onTap: onTap,
          customBorder: const CircleBorder(),
          child: const Padding(
            padding: EdgeInsets.all(10),
            child: Icon(
              Icons.keyboard_arrow_down_rounded,
              color: AppColors.primary,
              size: 24,
            ),
          ),
        ),
      ),
    );
  }
}

class _ChatPatternBackground extends StatelessWidget {
  const _ChatPatternBackground();

  static const _icons = [
    Icons.panorama_fish_eye,
    Icons.crop_square,
    Icons.star_border_rounded,
    Icons.adjust,
    Icons.radio_button_unchecked,
    Icons.change_history_outlined,
    Icons.language_outlined,
    Icons.watch_later_outlined,
    Icons.crop_16_9_outlined,
    Icons.account_circle_outlined,
  ];

  @override
  Widget build(BuildContext context) {
    return IgnorePointer(
      child: Opacity(
        opacity: 0.045,
        child: GridView.builder(
          physics: const NeverScrollableScrollPhysics(),
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
          gridDelegate: const SliverGridDelegateWithFixedCrossAxisCount(
            crossAxisCount: 5,
            mainAxisSpacing: 18,
            crossAxisSpacing: 16,
          ),
          itemCount: 120,
          itemBuilder: (context, index) {
            final icon = _icons[index % _icons.length];
            return Icon(icon, size: 22, color: const Color(0xFF7D8798));
          },
        ),
      ),
    );
  }
}

enum _ChatMenuAction { search, close, transfer, media, favorites, notes }

enum _ChatQuickAction {
  documents,
  photosVideos,
  camera,
  currentLocation,
  companyLocation,
  contact,
  internalNote,
  stickers,
}

enum _MediaKind { image, video }

class _ChatQuickActionsSheet extends StatelessWidget {
  const _ChatQuickActionsSheet({required this.onSelected});

  final ValueChanged<_ChatQuickAction> onSelected;

  @override
  Widget build(BuildContext context) {
    final maxHeight = MediaQuery.of(context).size.height * 0.7;

    const items = <_QuickActionItem>[
      _QuickActionItem(
        action: _ChatQuickAction.documents,
        label: 'Documentos',
        icon: Icons.description_outlined,
        iconColor: Color(0xFF8B5CF6),
        iconBackground: Color(0xFFF3E8FF),
      ),
      _QuickActionItem(
        action: _ChatQuickAction.photosVideos,
        label: 'Fotos e Videos',
        icon: Icons.photo_library_outlined,
        iconColor: Color(0xFFEC4899),
        iconBackground: Color(0xFFFCE7F3),
      ),
      _QuickActionItem(
        action: _ChatQuickAction.camera,
        label: 'Camera',
        icon: Icons.photo_camera_outlined,
        iconColor: Color(0xFFEF4444),
        iconBackground: Color(0xFFFEE2E2),
      ),
      _QuickActionItem(
        action: _ChatQuickAction.currentLocation,
        label: 'Localizacao atual',
        icon: Icons.my_location_rounded,
        iconColor: Color(0xFF22C55E),
        iconBackground: Color(0xFFDCFCE7),
      ),
      _QuickActionItem(
        action: _ChatQuickAction.companyLocation,
        label: 'Localizacao da empresa',
        icon: Icons.apartment_rounded,
        iconColor: Color(0xFF3B82F6),
        iconBackground: Color(0xFFDBEAFE),
      ),
      _QuickActionItem(
        action: _ChatQuickAction.contact,
        label: 'Contato',
        icon: Icons.person_add_alt_1_rounded,
        iconColor: Color(0xFFF97316),
        iconBackground: Color(0xFFFFEDD5),
      ),
      _QuickActionItem(
        action: _ChatQuickAction.internalNote,
        label: 'Nota interna',
        icon: Icons.note_alt_outlined,
        iconColor: Color(0xFF7C3AED),
        iconBackground: Color(0xFFEDE9FE),
      ),
      _QuickActionItem(
        action: _ChatQuickAction.stickers,
        label: 'Figurinhas',
        icon: Icons.emoji_emotions_outlined,
        iconColor: Color(0xFF06B6D4),
        iconBackground: Color(0xFFCCFBF1),
      ),
    ];

    return SafeArea(
      top: false,
      child: Padding(
        padding: const EdgeInsets.fromLTRB(8, 0, 8, 10),
        child: Material(
          color: Colors.white,
          borderRadius: BorderRadius.circular(22),
          child: Container(
            padding: const EdgeInsets.symmetric(vertical: 6),
            decoration: BoxDecoration(
              borderRadius: BorderRadius.circular(22),
              border: Border.all(color: const Color(0xFFE5E7EB)),
            ),
            child: ConstrainedBox(
              constraints: BoxConstraints(maxHeight: maxHeight),
              child: ListView.separated(
                shrinkWrap: true,
                itemCount: items.length,
                separatorBuilder: (_, __) => const SizedBox(height: 2),
                itemBuilder: (context, index) {
                  final item = items[index];
                  return ListTile(
                    onTap: () => onSelected(item.action),
                    leading: Container(
                      width: 36,
                      height: 36,
                      decoration: BoxDecoration(
                        color: item.iconBackground,
                        shape: BoxShape.circle,
                      ),
                      child: Icon(item.icon, color: item.iconColor, size: 21),
                    ),
                    title: Text(
                      item.label,
                      style: const TextStyle(
                        color: Color(0xFF1F2937),
                        fontSize: 17,
                        fontWeight: FontWeight.w500,
                      ),
                    ),
                  );
                },
              ),
            ),
          ),
        ),
      ),
    );
  }
}

class _QuickActionItem {
  const _QuickActionItem({
    required this.action,
    required this.label,
    required this.icon,
    required this.iconColor,
    required this.iconBackground,
  });

  final _ChatQuickAction action;
  final String label;
  final IconData icon;
  final Color iconColor;
  final Color iconBackground;
}
