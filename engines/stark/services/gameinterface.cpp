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

#include "engines/stark/services/gameinterface.h"

#include "engines/stark/debug.h"

#include "engines/stark/movement/directwalk.h"
#include "engines/stark/movement/walk.h"

#include "engines/stark/resources/anim.h"
#include "engines/stark/resources/knowledgeset.h"
#include "engines/stark/resources/level.h"
#include "engines/stark/resources/location.h"
#include "engines/stark/resources/speech.h"

#include "engines/stark/resources/floor.h"
#include "engines/stark/resources/floorface.h"
#include "engines/stark/resources/script.h"
#include "engines/stark/resources/item.h"

#include "engines/stark/services/global.h"
#include "engines/stark/services/services.h"

#include "engines/stark/gfx/driver.h"

#include "engines/stark/visual/image.h"

#include "engines/stark/scene.h"
#include "engines/stark/services/userinterface.h"

namespace Stark {

GameInterface::GameInterface() : _autoExitItem(nullptr) {
}

GameInterface::~GameInterface() {
}

bool GameInterface::skipCurrentSpeeches() {
	Current *current = StarkGlobal->getCurrent();

	if (!current) {
		return false; // No current location, nothing to do
	}

	// Get all speeches
	Common::Array<Resources::Speech *> speeches;
	speeches.push_back(StarkGlobal->getLevel()->listChildrenRecursive<Resources::Speech>());
	speeches.push_back(current->getLevel()->listChildrenRecursive<Resources::Speech>());
	speeches.push_back(current->getLocation()->listChildrenRecursive<Resources::Speech>());

	// Stop them
	bool skippedSpeeches = false;
	for (uint i = 0; i < speeches.size(); i++) {
		Resources::Speech *speech = speeches[i];
		if (speech->isPlaying()) {
			speech->stop();
			skippedSpeeches = true;
		}
	}

	return skippedSpeeches;
}

void GameInterface::walkTo(const Common::Point &mouse) {
	Resources::Floor *floor = StarkGlobal->getCurrent()->getFloor();
	Resources::ModelItem *april = StarkGlobal->getCurrent()->getInteractive();
	if (!floor || !april) {
		return;
	}

	Math::Ray mouseRay = StarkScene->makeRayFromMouse(mouse);

	// First look for a direct intersection with the floor
	Math::Vector3d destinationPosition;
	int32 destinationFloorFaceIndex = floor->findFaceHitByRay(mouseRay, destinationPosition);

	// Otherwise fall back to the floor face center closest to the ray
	if (destinationFloorFaceIndex < 0) {
		destinationFloorFaceIndex = floor->findFaceClosestToRay(mouseRay, destinationPosition);
	}

	if (destinationFloorFaceIndex < 0) {
		// No destination was found
		return;
	}

	Walk *walk = new Walk(april);
	walk->setDestination(destinationPosition);
	walk->start();

	april->setMovement(walk);
}

void GameInterface::directWalk(float x, float y) {
	if (!StarkUserInterface->isInteractive() || !StarkUserInterface->isInGameScreen()) {
		return;
	}

	Current *current = StarkGlobal->getCurrent();
	if (!current) {
		return;
	}

	Resources::Floor *floor = current->getFloor();
	Resources::ModelItem *april = current->getInteractive();
	if (!floor || !april || !april->isEnabled()) {
		return;
	}

	Movement *movement = april->getMovement();
	DirectWalk *directWalk = nullptr;
	if (movement && movement->getType() == Movement::kTypeDirectWalk) {
		directWalk = static_cast<DirectWalk *>(movement);
	}

	if (!directWalk) {
		if (x == 0.f && y == 0.f) {
			// Don't interrupt other movements when the stick is released
			return;
		}

		directWalk = new DirectWalk(april);
		directWalk->setInputVector(x, y);
		directWalk->start();

		april->setMovement(directWalk);
	} else {
		// The movement stops itself on the next game loop when the vector is null
		directWalk->setInputVector(x, y);
	}
}

VisualImageXMG *GameInterface::getActionImage(uint32 itemIndex, bool active) {
	// Lookup the action's item in the inventory
	Resources::KnowledgeSet *inventory = StarkGlobal->getLevel()->findChildWithSubtype<Resources::KnowledgeSet>(Resources::KnowledgeSet::kInventory, true);

	// Get the visual for the action
	Resources::InventoryItem *action = inventory->findChildWithIndex<Resources::InventoryItem>(itemIndex);
	Visual *visual = action->getActionVisual(active);

	return visual->get<VisualImageXMG>();
}

VisualImageXMG *GameInterface::getCursorImage(uint32 itemIndex) {
	// Lookup the item's item in the inventory
	Resources::KnowledgeSet *inventory = StarkGlobal->getLevel()->findChildWithSubtype<Resources::KnowledgeSet>(Resources::KnowledgeSet::kInventory, true);

	// Get the visual for the item
	Resources::InventoryItem *item = inventory->findChildWithIndex<Resources::InventoryItem>(itemIndex);
	Visual *visual = item->getCursorVisual();

	return visual->get<VisualImageXMG>();
}

bool GameInterface::itemHasAction(Resources::ItemVisual *item, int32 action) {
	if (action != -1) {
		return item->canPerformAction(action, 0);
	} else {
		Resources::ActionArray actions = listActionsPossibleForObject(item);
		return !actions.empty();
	}
}

bool GameInterface::itemHasActionAt(Resources::ItemVisual *item, const Common::Point &position, int32 action) {
	int32 hotspotIndex = item->getHotspotIndexForPoint(position);
	if (action != -1) {
		return item->canPerformAction(action, hotspotIndex);
	} else {
		Resources::ActionArray actions = listActionsPossibleForObjectAt(item, position);
		return !actions.empty();
	}
}

int32 GameInterface::itemGetDefaultActionAt(Resources::ItemVisual *item, const Common::Point &position) {
	int32 hotspotIndex = item->getHotspotIndexForPoint(position);
	Resources::PATTable *table = item->findChildWithOrder<Resources::PATTable>(hotspotIndex);
	if (table) {
		return table->getDefaultAction();
	} else {
		return -1;
	}
}

void GameInterface::itemDoAction(Resources::ItemVisual *item, uint32 action) {
	item->doAction(action, 0);
}

void GameInterface::itemDoActionAt(Resources::ItemVisual *item, uint32 action, const Common::Point &position) {
	int32 hotspotIndex = item->getHotspotIndexForPoint(position);
	item->doAction(action, hotspotIndex);
}

Common::String GameInterface::getItemTitle(Resources::ItemVisual *item) {
	return item->getHotspotTitle(0);
}

Common::String GameInterface::getItemTitleAt(Resources::ItemVisual *item, const Common::Point &pos) {
	int32 hotspotIndex = item->getHotspotIndexForPoint(pos);
	return item->getHotspotTitle(hotspotIndex);
}

Resources::ActionArray GameInterface::listActionsPossibleForObject(Resources::ItemVisual *item) {
	if (item == nullptr) {
		return Resources::ActionArray();
	}

	Resources::PATTable *table = item->findChildWithOrder<Resources::PATTable>(0);
	if (table) {
		return table->listPossibleActions();
	} else {
		return Resources::ActionArray();
	}
}

Resources::ActionArray GameInterface::listActionsPossibleForObjectAt(Resources::ItemVisual *item,
																	 const Common::Point &pos) {
	if (item == nullptr) {
		return Resources::ActionArray();
	}

	int index = item->getHotspotIndexForPoint(pos);
	if (index < 0) {
		return Resources::ActionArray();
	}

	Resources::PATTable *table = item->findChildWithOrder<Resources::PATTable>(index);
	if (table) {
		return table->listPossibleActions();
	} else {
		return Resources::ActionArray();
	}
}

Resources::ActionArray GameInterface::listStockActionsPossibleForObject(Resources::ItemVisual *item) {
	Resources::ActionArray actions = listActionsPossibleForObject(item);

	Resources::ActionArray stockActions;
	for (uint i = 0; i < actions.size(); i++) {
		if (actions[i] < 4) {
			stockActions.push_back(actions[i]);
		}
	}

	return stockActions;
}

Resources::ActionArray GameInterface::listStockActionsPossibleForObjectAt(Resources::ItemVisual *item,
																		  const Common::Point &pos) {
	Resources::ActionArray actions = listActionsPossibleForObjectAt(item, pos);

	Resources::ActionArray stockActions;
	for (uint i = 0; i < actions.size(); i++) {
		if (actions[i] < 4) {
			stockActions.push_back(actions[i]);
		}
	}

	return stockActions;
}


bool GameInterface::isAprilWalking() const {
	Current *current = StarkGlobal->getCurrent();
	if (!current) {
		return false;
	}

	Resources::ModelItem *april = current->getInteractive();
	if (!april) {
		return false;
	}

	Movement *movement = april->getMovement();
	if (!movement) {
		return false;
	}

	Walk *walk = dynamic_cast<Walk *>(movement);
	if (!walk) {
		return false;
	}

	return !walk->hasEnded();
}

void GameInterface::setAprilRunning() {
	Current *current = StarkGlobal->getCurrent();
	Resources::ModelItem *april = current->getInteractive();
	Movement *movement = april->getMovement();
	Walk *walk = dynamic_cast<Walk *>(movement);

	assert(walk);
	walk->setRunning();
}

Common::Array<Common::Point> GameInterface::listExitPositions() {
	return StarkGlobal->getCurrent()->getLocation()->listExitPositions();
}

bool GameInterface::tryAutoExit() {
	if (!StarkUserInterface->isInteractive() || !StarkUserInterface->isInGameScreen()) {
		return false;
	}

	Current *current = StarkGlobal->getCurrent();
	if (!current) {
		return false;
	}

	Resources::ModelItem *april = current->getInteractive();
	Resources::Location *location = current->getLocation();
	Resources::Floor *floor = current->getFloor();
	if (!april || !location || !floor) {
		return false;
	}

	Resources::Anim *anim = april->getAnim();
	if (!anim) {
		return false;
	}

	// The exit triggers when the character could reach it by walking for
	// about half a second. This scales the radius to the world's units.
	float triggerRadius = anim->getMovementSpeed() * 0.5f;
	if (triggerRadius <= 0.f) {
		return false;
	}

	Math::Vector3d aprilPosition = april->getPosition3D();

	Common::Array<Resources::Item *> items = location->listChildrenRecursive<Resources::Item>();

	Resources::ItemVisual *exitItem = nullptr;
	Common::Point exitPosition;
	float bestDistance = triggerRadius;

	for (uint i = 0; i < items.size(); i++) {
		if (!items[i]->isEnabled()) {
			continue;
		}

		Common::Array<Common::Point> exitPositions = items[i]->listExitPositions();
		for (uint j = 0; j < exitPositions.size(); j++) {
			// Cast the exit hotspot onto the walkable floor, using the same
			// code path as clicking it (see walkTo). This gives the position
			// the character would walk to when using the exit.
			Common::Point screenPos(exitPositions[j].x, exitPositions[j].y + Gfx::Driver::kTopBorderHeight);
			Common::Point currentPos = StarkGfx->convertCoordinateOriginalToCurrent(screenPos);

			Math::Ray ray = StarkScene->makeRayFromMouse(currentPos);

			Math::Vector3d exitFloorPosition;
			int32 faceIndex = floor->findFaceHitByRay(ray, exitFloorPosition);
			if (faceIndex < 0) {
				faceIndex = floor->findFaceClosestToRay(ray, exitFloorPosition);
			}
			if (faceIndex < 0) {
				continue;
			}

			float distance = aprilPosition.getDistanceTo(exitFloorPosition);

			debugC(3, kDebugUnknown, "tryAutoExit: exit=(%d,%d) dist=%f radius=%f",
			       exitPositions[j].x, exitPositions[j].y, distance, triggerRadius);

			if (distance < bestDistance) {
				bestDistance = distance;
				exitItem = Resources::Object::cast<Resources::ItemVisual>(items[i]);
				exitPosition = exitPositions[j];
			}
		}
	}

	if (!exitItem) {
		_autoExitItem = nullptr;
		return false;
	}

	if (exitItem == _autoExitItem) {
		// This exit was already triggered, wait for the character to move away
		return false;
	}

	Gfx::RenderEntry *exitRenderEntry = exitItem->getRenderEntry(location->getScrollPosition());
	if (!exitRenderEntry) {
		return false;
	}

	// The hotspot lookup expects item relative coordinates
	Common::Point exitRelativePosition = exitPosition - exitRenderEntry->getPosition();

	_autoExitItem = exitItem;
	itemDoActionAt(exitItem, Resources::PATTable::kActionExit, exitRelativePosition);

	return true;
}

} // End of namespace Stark
