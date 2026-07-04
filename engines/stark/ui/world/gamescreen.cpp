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

#include "engines/stark/ui/world/gamescreen.h"
#include "engines/stark/services/services.h"
#include "engines/stark/services/userinterface.h"
#include "engines/stark/services/gameinterface.h"
#include "engines/stark/services/global.h"
#include "engines/stark/gfx/driver.h"
#include "engines/stark/ui/cursor.h"
#include "engines/stark/ui/world/actionmenu.h"
#include "engines/stark/ui/world/dialogpanel.h"
#include "engines/stark/ui/world/gamewindow.h"
#include "engines/stark/ui/world/inventorywindow.h"
#include "engines/stark/ui/world/topmenu.h"
#include "engines/stark/resources/level.h"
#include "engines/stark/resources/location.h"

namespace Stark {

GameScreen::GameScreen(Gfx::Driver *gfx, Cursor *cursor) :
		Screen(Screen::kScreenGame),
		_gfx(gfx),
		_cursor(cursor) {

	_topMenu = new TopMenu(_gfx, _cursor);
	_dialogPanel = new DialogPanel(_gfx, _cursor);
	_actionMenu = new ActionMenu(_gfx, _cursor);
	_inventoryWindow = new InventoryWindow(_gfx, _cursor, _actionMenu);
	_actionMenu->setInventory(_inventoryWindow);
	_gameWindow = new GameWindow(_gfx, _cursor, _actionMenu, _inventoryWindow);

	_gameScreenWindows.push_back(_actionMenu);
	_gameScreenWindows.push_back(_inventoryWindow);
	_gameScreenWindows.push_back(_gameWindow);
	_gameScreenWindows.push_back(_topMenu);
	_gameScreenWindows.push_back(_dialogPanel);
}

GameScreen::~GameScreen() {
	delete _gameWindow;
	delete _actionMenu;
	delete _topMenu;
	delete _dialogPanel;
	delete _inventoryWindow;
}

void GameScreen::open() {
	pauseGame(false);
	StarkUserInterface->freeGameScreenThumbnail();
}

void GameScreen::close() {
	_cursor->setMouseHint("");
	pauseGame(true);
	StarkUserInterface->saveGameScreenThumbnail();
}

void GameScreen::handleGameLoop() {
	for (int i = _gameScreenWindows.size() - 1; i >= 0; i--) {
		_gameScreenWindows[i]->handleGameLoop();
	}
}

void GameScreen::render() {
	for (int i = _gameScreenWindows.size() - 1; i >= 0; i--) {
		_gameScreenWindows[i]->render();
	}
}

InventoryWindow *GameScreen::getInventoryWindow() const {
	return _inventoryWindow;
}

void GameScreen::reset() {
	_dialogPanel->reset();
	_gameWindow->reset();
	_inventoryWindow->reset();
	_actionMenu->close();
}

GameWindow *GameScreen::getGameWindow() const {
	return _gameWindow;
}

DialogPanel *GameScreen::getDialogPanel() const {
	return _dialogPanel;
}

void GameScreen::handleMouseMove() {
	dispatchEvent(&Window::handleMouseMove);
}

void GameScreen::handleClick() {
	dispatchEvent(&Window::handleClick);
}

void GameScreen::handleRightClick() {
	dispatchEvent(&Window::handleRightClick);
}

void GameScreen::handleDoubleClick() {
	dispatchEvent(&Window::handleDoubleClick);
}

void GameScreen::handleGridNavigation(GridDirection direction) {
	if (_actionMenu->isVisible()) {
		_actionMenu->navigateGrid(direction);
	} else if (_inventoryWindow->isVisible()) {
		_inventoryWindow->navigateGrid(direction);
	} else if (_dialogPanel->hasOptions()) {
		if (direction == kGridDirectionUp) {
			_dialogPanel->focusPrevOption();
		} else if (direction == kGridDirectionDown) {
			_dialogPanel->focusNextOption();
		} else {
			return;
		}

		_dialogPanel->snapCursorToFocusedOption();
	} else {
		// Plain gameplay: jump the cursor to an exit so it can be triggered
		// with a single tap instead of dragging it across the screen
		snapCursorToExit(direction);
	}
}

void GameScreen::snapCursorToExit(GridDirection direction) {
	if (!StarkUserInterface->isInteractive()) {
		return;
	}

	Common::Array<Common::Point> exitPositions = StarkGameInterface->listExitCenters();
	if (exitPositions.empty()) {
		return;
	}

	// The exit positions are in game window coordinates. Bring them into the
	// original screen coordinates the cursor uses by adding the top border.
	Common::Point cursor = _cursor->getMousePosition();

	int dirX = (direction == kGridDirectionRight) - (direction == kGridDirectionLeft);
	int dirY = (direction == kGridDirectionDown) - (direction == kGridDirectionUp);

	int bestDirected = -1;
	int bestDirectedDistSq = 0;
	int bestAny = -1;
	int bestAnyDistSq = 0;

	for (uint i = 0; i < exitPositions.size(); i++) {
		Common::Point exitPoint(exitPositions[i].x, exitPositions[i].y + Gfx::Driver::kTopBorderHeight);

		int dx = exitPoint.x - cursor.x;
		int dy = exitPoint.y - cursor.y;
		int distSq = dx * dx + dy * dy;

		if (bestAny < 0 || distSq < bestAnyDistSq) {
			bestAny = i;
			bestAnyDistSq = distSq;
		}

		// Is the exit in the pressed direction, and mostly along that axis?
		int along = dx * dirX + dy * dirY;
		int across = ABS(dx * dirY) + ABS(dy * dirX);
		if (along > 0 && along >= across) {
			if (bestDirected < 0 || distSq < bestDirectedDistSq) {
				bestDirected = i;
				bestDirectedDistSq = distSq;
			}
		}
	}

	int chosen = bestDirected >= 0 ? bestDirected : bestAny;
	Common::Point target(exitPositions[chosen].x,
	                     exitPositions[chosen].y + Gfx::Driver::kTopBorderHeight);

	// Briefly show the exit indicators so the player sees where the cursor went
	_gameWindow->showExitsBriefly();

	StarkUserInterface->warpMouseTo(target);
}

void GameScreen::dispatchEvent(WindowHandler handler) {
	for (uint i = 0; i < _gameScreenWindows.size(); i++) {
		if (_gameScreenWindows[i]->isMouseInside()) {
			(*_gameScreenWindows[i].*handler)();
			return;
		}
	}
}

void GameScreen::onScreenChanged() {
	_cursor->onScreenChanged();
	_dialogPanel->onScreenChanged();
	_topMenu->onScreenChanged();
	_gameWindow->onScreenChanged();
	_actionMenu->onScreenChanged();
}

void GameScreen::notifyInventoryItemEnabled(uint16 itemIndex) {
	_topMenu->notifyInventoryItemEnabled(itemIndex);
}

void GameScreen::notifyDiaryEntryEnabled() {
	_topMenu->notifyDiaryEntryEnabled();
}

void GameScreen::pauseGame(bool pause) {
	if (StarkGlobal->getLevel()) {
		StarkGlobal->getLevel()->onEnginePause(pause);
	}
	if (StarkGlobal->getCurrent()) {
		StarkGlobal->getCurrent()->getLevel()->onEnginePause(pause);
		StarkGlobal->getCurrent()->getLocation()->onEnginePause(pause);
	}
}

} // End of namespace Stark
