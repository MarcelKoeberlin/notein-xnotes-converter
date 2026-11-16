-- Notein note database schema (Room DB version 34, identity hash 6fb07f1830e43b74e35643c931edda69),
-- taken from a Notein export. Used to build .in files.
CREATE TABLE `NoteContentEntity` (`id` TEXT NOT NULL, `page_list` TEXT, `page_layer_list` TEXT, `outline_list` TEXT NOT NULL, `default_page_id` TEXT NOT NULL, `pdf_info_id` TEXT, `saved_page_index` INTEGER NOT NULL, `activated_page_layer_id` TEXT NOT NULL, `zoom` REAL NOT NULL, `unbounded_page_offset_x` REAL NOT NULL, `unbounded_page_offset_y` REAL NOT NULL, `unbounded_note` INTEGER NOT NULL, `creation_time` INTEGER NOT NULL, `last_modification_time` INTEGER NOT NULL, extras TEXT NOT NULL DEFAULT '{}', page_offset_json TEXT NOT NULL DEFAULT '{"offset_x":0,"offset_y":0}', PRIMARY KEY(`id`));
CREATE TABLE `PageEntity` (`id` TEXT NOT NULL, `note_id` TEXT NOT NULL, `paper_spec` TEXT, `page_orientation` TEXT NOT NULL, `paper_theme` TEXT, `creation_time` INTEGER NOT NULL, `last_modification_time` INTEGER NOT NULL, `tn_path` TEXT NOT NULL, `unbounded` INTEGER NOT NULL, `source` INTEGER NOT NULL, `recover_note_id` TEXT NOT NULL, `recover_note_title` TEXT NOT NULL, `recover_index` INTEGER NOT NULL, `is_in_trash_bin` INTEGER NOT NULL, `history_page_id_list` TEXT, paper_padding TEXT DEFAULT NULL, padding_color INTEGER NOT NULL DEFAULT -1, rotation_direction_index INTEGER NOT NULL DEFAULT 0, padding_style_json TEXT DEFAULT NULL, is_bookmarked INTEGER NOT NULL DEFAULT 0, bookmark_time INTEGER NOT NULL DEFAULT 0, PRIMARY KEY(`id`));
CREATE TABLE `PdfInfoEntity` (`id` TEXT NOT NULL, `pdf_path` TEXT NOT NULL, `tn_path` TEXT NOT NULL, `password` TEXT, PRIMARY KEY(`id`));
CREATE TABLE `StrokeEntity` (`id` TEXT NOT NULL, `page_id` TEXT NOT NULL, `layer_id` TEXT NOT NULL, `creation_time` INTEGER NOT NULL, `record_json` TEXT, `left` REAL, `top` REAL, `right` REAL, `bottom` REAL, ink_stroke_json TEXT DEFAULT NULL, ink_stroke_blob BLOB DEFAULT NULL, PRIMARY KEY(`id`));
CREATE TABLE `ImageEntity` (`id` TEXT NOT NULL, `uri` TEXT NOT NULL, `layer` INTEGER NOT NULL, `layer_id` TEXT NOT NULL, `bounds` TEXT, `rotation` REAL NOT NULL, `page_id` TEXT NOT NULL, `creation_time` INTEGER NOT NULL, `last_modification_time` INTEGER NOT NULL, `left` REAL, `top` REAL, `right` REAL, `bottom` REAL, `fixed` INTEGER NOT NULL, PRIMARY KEY(`id`));
CREATE TABLE `OutlineEntity` (`id` TEXT NOT NULL, `title` TEXT NOT NULL, `parent_id` TEXT, `page_id` TEXT NOT NULL, `note_id` TEXT NOT NULL, `quote_id` TEXT, `children` TEXT NOT NULL, creation_time INTEGER NOT NULL DEFAULT 0, last_modification_time INTEGER NOT NULL DEFAULT 0, PRIMARY KEY(`id`));
CREATE TABLE `CommentEntity` (`id` TEXT NOT NULL, `title` TEXT NOT NULL, `page_id` TEXT NOT NULL, `note_id` TEXT NOT NULL, `quote_id` TEXT, `creation_time` INTEGER NOT NULL, `last_modification_time` INTEGER NOT NULL, sort_key INTEGER DEFAULT NULL, PRIMARY KEY(`id`));
CREATE TABLE `QuoteEntity` (`id` TEXT NOT NULL, `page_id` TEXT NOT NULL, `type` INTEGER NOT NULL, `color` INTEGER NOT NULL, `label_rect` TEXT NOT NULL, `rect_list` TEXT NOT NULL, `text` TEXT NOT NULL, `link_type` INTEGER NOT NULL, `link_id` TEXT NOT NULL, `layer_id` TEXT NOT NULL, `creation_time` INTEGER NOT NULL, bg_color INTEGER NOT NULL DEFAULT 0, underline_color INTEGER NOT NULL DEFAULT 0, anno_item_id_list TEXT, is_vertical_pdf_text INTEGER NOT NULL DEFAULT 0, is_rtl_or_btt_pdf_text INTEGER NOT NULL DEFAULT 0, PRIMARY KEY(`id`));
CREATE TABLE `TextBoxEntity` (`id` TEXT NOT NULL, `page_id` TEXT NOT NULL, `text` TEXT NOT NULL, `text_size` REAL NOT NULL, `box_width` REAL NOT NULL, `box_height` REAL NOT NULL, `line_height` REAL NOT NULL, `background_color` INTEGER NOT NULL, `bounds` TEXT, `layer` INTEGER NOT NULL, `layer_id` TEXT NOT NULL, `default_text_color` INTEGER NOT NULL, `creation_time` INTEGER NOT NULL, `left` REAL, `top` REAL, `right` REAL, `bottom` REAL, local_transform_json TEXT DEFAULT NULL, fixed INTEGER NOT NULL DEFAULT(0), metrics_version INTEGER NOT NULL DEFAULT(0), PRIMARY KEY(`id`));
CREATE TABLE `ShapeEntity` (`id` TEXT NOT NULL, `page_id` TEXT NOT NULL, `color` INTEGER NOT NULL, `width` REAL NOT NULL, `points` TEXT NOT NULL, `type` INTEGER NOT NULL, `blend_mode` INTEGER NOT NULL, `layer_id` TEXT NOT NULL, `tape_like` INTEGER NOT NULL, `style` INTEGER NOT NULL, `opacity_of_fill_color` INTEGER NOT NULL, `creation_time` INTEGER NOT NULL, `left` REAL, `top` REAL, `right` REAL, `bottom` REAL, tape_pattern INTEGER NOT NULL DEFAULT 0, PRIMARY KEY(`id`));
CREATE TABLE `DualLinkRefEntity` (`id` TEXT NOT NULL, `note_id` TEXT NOT NULL, `page_id` TEXT NOT NULL, `bounds` TEXT NOT NULL, `item_id` TEXT, `source_id` TEXT, `source_note_id` TEXT, `creation_time` INTEGER NOT NULL, `last_modification_time` INTEGER NOT NULL, `left` REAL, `top` REAL, `right` REAL, `bottom` REAL, PRIMARY KEY(`id`));
CREATE TABLE `DualLinkSourceEntity` (`id` TEXT NOT NULL, `note_id` TEXT NOT NULL, `page_id` TEXT NOT NULL, `type` INTEGER NOT NULL, `bounds` TEXT NOT NULL, `text_bounds` TEXT NOT NULL, `ref_id` TEXT, `ref_note_id` TEXT, `creation_time` INTEGER NOT NULL, `last_modification_time` INTEGER NOT NULL, `left` REAL, `top` REAL, `right` REAL, `bottom` REAL, PRIMARY KEY(`id`));
CREATE TABLE `PageLayerEntity` (`id` TEXT NOT NULL, `note_id` TEXT NOT NULL, `visible` INTEGER NOT NULL, `extras` TEXT, name TEXT DEFAULT NULL, PRIMARY KEY(`id`));
CREATE TABLE `HyperLinkEntity` (`id` TEXT NOT NULL, `bounds` TEXT, `page_id` TEXT NOT NULL, `type` INTEGER NOT NULL, `destination` TEXT NOT NULL, `extras` TEXT, 'creation_time' INTEGER NOT NULL, 'last_modification_time' INTEGER NOT NULL, 'left' REAL, 'right' REAL, 'top' REAL, 'bottom' REAL, PRIMARY KEY(`id`));
CREATE TABLE `QuoteTextAnnoEntity` (`id` TEXT NOT NULL, `username` TEXT NOT NULL, `type` INTEGER NOT NULL, `text` TEXT NOT NULL, `creation_time` INTEGER NOT NULL, `last_modified_time` INTEGER NOT NULL, PRIMARY KEY(`id`));
CREATE TABLE `AudioFileEntity` (`id` TEXT NOT NULL, `file_path` TEXT NOT NULL, `audio_name` TEXT NOT NULL, `duration` INTEGER NOT NULL, `play_speed` REAL NOT NULL, `creation_time` INTEGER NOT NULL, `last_modification_time` INTEGER NOT NULL, PRIMARY KEY(`id`));
CREATE TABLE `AudioSyncRecordEntity` (`id` TEXT NOT NULL, `audio_id` TEXT NOT NULL, `audio_position` INTEGER NOT NULL, `display_item_id` TEXT NOT NULL, `display_item_type` INTEGER NOT NULL, `creation_time` INTEGER NOT NULL, `last_modification_time` INTEGER NOT NULL, 'deleted' INTEGER NOT NULL, PRIMARY KEY(`id`));
CREATE TABLE `NoteAudioFileIdsFieldEntity` (`id` TEXT NOT NULL, `note_id` TEXT NOT NULL, `audio_file_ids` TEXT NOT NULL, PRIMARY KEY(`id`));
CREATE TABLE `TableBlockEntity` (`id` TEXT NOT NULL, `page_id` TEXT NOT NULL, `columns_json` TEXT NOT NULL, `rows_json` TEXT NOT NULL, `cells_json` TEXT NOT NULL, `style_json` TEXT, `bounds` TEXT, `layer_id` TEXT NOT NULL, `creation_time` INTEGER NOT NULL, `local_transform_json` TEXT, `left` REAL, `top` REAL, `right` REAL, `bottom` REAL, `fixed` INTEGER NOT NULL, `schema_version` INTEGER NOT NULL, PRIMARY KEY(`id`));
CREATE TABLE `BeautifiedChunkEntity` (
  `id` TEXT NOT NULL,
  `page_id` TEXT NOT NULL,
  `layer_id` TEXT NOT NULL,
  `left` REAL NOT NULL,
  `top` REAL NOT NULL,
  `right` REAL NOT NULL,
  `bottom` REAL NOT NULL,
  `char_size` REAL NOT NULL,
  `char_spacing` REAL NOT NULL,
  `line_height` REAL NOT NULL,
  `line_spacing` REAL NOT NULL DEFAULT 0,
  `created_at` INTEGER NOT NULL,
  `updated_at` INTEGER NOT NULL,
  `grid_origin_x` REAL NOT NULL DEFAULT 0,
  `grid_origin_y` REAL NOT NULL DEFAULT 0,
  `row_count` INTEGER NOT NULL DEFAULT 1,
  `column_count` INTEGER NOT NULL DEFAULT 1,
  `char_states` TEXT NOT NULL DEFAULT '',
  `snapped_to_page_grid` INTEGER NOT NULL DEFAULT 0,
  `column_unit` INTEGER NOT NULL DEFAULT 1,
  PRIMARY KEY(`id`)
);
CREATE INDEX `index_BeautifiedChunkEntity_page_layer` ON `BeautifiedChunkEntity` (`page_id`, `layer_id`);
CREATE TABLE `GlyphEntity` (
  `id` TEXT NOT NULL,
  `page_id` TEXT NOT NULL,
  `char` TEXT NOT NULL,
  `font_id` TEXT NOT NULL,
  `font_size` REAL NOT NULL,
  `color` INTEGER NOT NULL,
  `bounds` TEXT,
  `layer_id` TEXT NOT NULL,
  `creation_time` INTEGER NOT NULL,
  `left` REAL,
  `top` REAL,
  `right` REAL,
  `bottom` REAL,
  `local_transform_json` TEXT,
  `chunk_id` TEXT NOT NULL DEFAULT '',
  `chunk_row` INTEGER NOT NULL DEFAULT 0,
  `chunk_col` INTEGER NOT NULL DEFAULT 0, restore_unit_id TEXT, source_ink_absent INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY(`id`)
);
CREATE INDEX `index_GlyphEntity_chunk_id` ON `GlyphEntity` (`chunk_id`);
CREATE INDEX `index_GlyphEntity_page_layer` ON `GlyphEntity` (`page_id`, `layer_id`);
CREATE TABLE `BeautifySourceStrokeEntity` (
  `id` TEXT NOT NULL,
  `page_id` TEXT NOT NULL,
  `layer_id` TEXT NOT NULL,
  `creation_time` INTEGER NOT NULL,
  `record_json` TEXT,
  `ink_stroke_json` TEXT,
  `ink_stroke_blob` BLOB,
  `left` REAL, `top` REAL, `right` REAL, `bottom` REAL,
  `chunk_id` TEXT NOT NULL,
  `chunk_row` INTEGER NOT NULL DEFAULT 0,
  `chunk_col` INTEGER NOT NULL DEFAULT 0,
  `archived_time` INTEGER NOT NULL, restore_unit_id TEXT, restore_reason TEXT,
  PRIMARY KEY(`id`)
);
CREATE INDEX `index_BeautifySourceStrokeEntity_chunk_id` ON `BeautifySourceStrokeEntity` (`chunk_id`);
CREATE INDEX `index_BeautifySourceStrokeEntity_chunk_cell` ON `BeautifySourceStrokeEntity` (`chunk_id`, `chunk_row`, `chunk_col`);
CREATE INDEX `index_BeautifySourceStrokeEntity_page_layer` ON `BeautifySourceStrokeEntity` (`page_id`, `layer_id`);
CREATE INDEX `index_GlyphEntity_restore_unit_id` ON `GlyphEntity` (`restore_unit_id`);
CREATE INDEX `index_BeautifySourceStrokeEntity_restore_unit_id` ON `BeautifySourceStrokeEntity` (`restore_unit_id`);
