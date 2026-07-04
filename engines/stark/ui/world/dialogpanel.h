/* ScummVM - Graphic Adventure Engine
 *
 * ScummVM is the legal property of its developers, whose names
 * are too numerous to list here. Please refer to the COPYRIGHT
 * file distributed with this source distribution.
 *
 * This program is free software: you can redistribute it and/or modify
 * it under the terms of the GNU General Public License as published by
 * the Free Software Foundation, either version 3 of the License, or
 * (at your option) any later version.
 *
 * This program is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 * GNU General Public License for more details.
 *
 * You should have received a copy of the GNU General Public License
 * along with this program.  If not, see <http://www.gnu.org/licenses/>.
 *
 */

#ifndef STARK_UI_DIALOG_PANEL_H
#define STARK_UI_DIALOG_PANEL_H

#include "engines/stark/ui/window.h"
#include "engines/stark/gfx/color.h"

#include "common/scummsys.h"
#include "common/str.h"
#include "common/str-array.h"
#include "common/array.h"
#include "common/rect.h"

namespace Stark {

class VisualImageXMG;
class VisualText;
class ClickText;

namespace Resources {
class Speech;
}

class DialogPanel : public Window {
public:
	DialogPanel(Gfx::Driver *gfx, Cursor *cursor);
	virtual ~DialogPanel();

	/** Abort the currently playing dialog */
	void reset();

	/** The screen resolution changed, rebuild the text accordingly */
	void onScreenChanged();

	/** Scroll up and down the panel */
	void scrollUp();
	void scrollDown();

	/** Select the next or previous option */
	void focusNextOption();
	void focusPrevOption();

	/** Select the focused option */
	void selectFocusedOption();

	/** Select an option by index */
	void selectOption(uint index);

	/** Are there dialog options currently displayed? */
	bool hasOptions() const { return !_options.empty(); }

	/** Absolute position of the focused option's center, for cursor snapping */
	Common::Point getFocusedOptionCenter() const;

	/**
	 * Teleport the cursor to the focused option.
	 *
	 * Used by the D-pad navigation so the cursor follows the focus.
	 * The hover logic is inhibited until the pointer actually moves,
	 * so it cannot override the focus.
	 */
	void snapCursorToFocusedOption();

	/**
	 * Move the focus to the option currently under the cursor, if any.
	 *
	 * Makes sure the D-pad navigation steps from the option the player
	 * sees targeted, even if the focus got out of sync with the cursor.
	 */
	void syncFocusToCursor();

protected:
	void onMouseMove(const Common::Point &pos) override;
	void onClick(const Common::Point &pos) override;
	void onRightClick(const Common::Point &pos) override;
	void onGameLoop() override;
	void onRender() override;

private:
	void updateSubtitleVisual();
	void clearSubtitleVisual();
	void updateDialogOptions();
	void clearOptions();
	void layoutOptions();
	void renderOptions();
	void renderScrollArrows() const;

	void updateFirstVisibleOption();
	void updateLastVisibleOption();

	VisualImageXMG *_passiveBackGroundImage;
	VisualImageXMG *_activeBackGroundImage;
	VisualImageXMG *_scrollUpArrowImage;
	VisualImageXMG *_scrollDownArrowImage;
	VisualImageXMG *_dialogOptionBullet;
	VisualText *_subtitleVisual;

	bool _scrollUpArrowVisible;
	bool _scrollDownArrowVisible;
	Common::Rect _scrollUpArrowRect;
	Common::Rect _scrollDownArrowRect;

	Resources::Speech *_currentSpeech;
	void abortCurrentSpeech();

	uint32 _firstVisibleOption, _lastVisibleOption;
	uint32 _focusedOption;
	Common::Array<ClickText*> _options;
	bool _acceptIdleMousePos;
	Common::Point _prevMousePos;

	const Gfx::Color _aprilColor = Gfx::Color(0xFF, 0xC0, 0x00);
	const Gfx::Color _otherColor = Gfx::Color(0xFF, 0x40, 0x40);
	static const uint32 _optionsTop = 4;
	static const uint32 _optionsLeft = 30;
	static const uint32 _optionsHeight = 80;
};

} // End of namespace Stark

#endif // STARK_UI_DIALOG_PANEL_H
