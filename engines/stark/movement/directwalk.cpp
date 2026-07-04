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

#include "engines/stark/movement/directwalk.h"

#include "engines/stark/resources/anim.h"
#include "engines/stark/resources/camera.h"
#include "engines/stark/resources/floor.h"
#include "engines/stark/resources/item.h"
#include "engines/stark/resources/location.h"

#include "engines/stark/services/global.h"
#include "engines/stark/services/services.h"
#include "engines/stark/services/stateprovider.h"

#include "math/matrix3.h"

namespace Stark {

const float DirectWalk::_runThreshold = 0.65f;

DirectWalk::DirectWalk(Resources::FloorPositionedItem *item) :
		Movement(item),
		_item3D(item),
		_inputX(0.f),
		_inputY(0.f),
		_running(false),
		_turnDirection(kTurnNone) {
}

DirectWalk::~DirectWalk() {
}

void DirectWalk::start() {
	Movement::start();

	changeItemAnim();

	Resources::Location *location = StarkGlobal->getCurrent()->getLocation();
	location->startFollowingCharacter();
}

void DirectWalk::stop(bool force) {
	Movement::stop(force);
	changeItemAnim();
}

void DirectWalk::setInputVector(float x, float y) {
	_inputX = x;
	_inputY = y;

	float magnitude = sqrtf(x * x + y * y);
	_running = magnitude > _runThreshold;
}

void DirectWalk::onGameLoop() {
	if (_inputX == 0.f && _inputY == 0.f) {
		stop();
		return;
	}

	Resources::Floor *floor = StarkGlobal->getCurrent()->getFloor();
	Resources::Camera *camera = StarkGlobal->getCurrent()->getCamera();
	if (!floor || !camera) {
		stop();
		return;
	}

	// Convert the camera relative input vector to a world space angle.
	// Zero degrees means walking away from the camera, positive angles
	// are towards the right of the screen. Item directions are measured
	// the same way as in Command::opItemPlaceDirection.
	Math::Angle inputAngle = Math::Angle::arcTangent2(_inputX, -_inputY);
	Math::Angle targetAngle = inputAngle + camera->getHorizontalAngle();

	Math::Matrix3 rot;
	rot.buildAroundZ(-targetAngle);

	Math::Vector3d direction(1.0, 0.0, 0.0);
	rot.transformVector(&direction);

	// If the angle between the current direction and the new one is too high,
	// make the character turn on itself until the angle is low enough
	Math::Vector3d currentDirection = _item3D->getDirectionVector();
	float directionDeltaAngle = computeAngleBetweenVectorsXYPlane(currentDirection, direction);

	if (ABS(directionDeltaAngle) > getAngularSpeed() + 0.1f) {
		_turnDirection = directionDeltaAngle < 0 ? kTurnLeft : kTurnRight;
	} else {
		_turnDirection = kTurnNone;
	}

	changeItemAnim();

	Math::Vector3d currentPosition = _item3D->getPosition3D();
	Math::Vector3d newPosition = currentPosition;

	if (_turnDirection == kTurnNone) {
		float distancePerGameloop = computeDistancePerGameLoop();

		Math::Vector3d step = direction * distancePerGameloop;
		Math::Vector3d candidate = currentPosition + step;

		int32 newFloorFaceIndex = floor->findFaceContainingPoint(candidate);
		if (newFloorFaceIndex < 0) {
			// The full step leaves the floor, try to slide along the walls
			// by moving on a single world axis at a time
			candidate = currentPosition + Math::Vector3d(step.x(), 0.f, 0.f);
			newFloorFaceIndex = floor->findFaceContainingPoint(candidate);

			if (newFloorFaceIndex < 0) {
				candidate = currentPosition + Math::Vector3d(0.f, step.y(), 0.f);
				newFloorFaceIndex = floor->findFaceContainingPoint(candidate);
			}
		}

		if (newFloorFaceIndex >= 0) {
			floor->computePointHeightInFace(candidate, newFloorFaceIndex);
			newPosition = candidate;

			_item3D->setPosition3D(newPosition);
			_item3D->setFloorFaceIndex(newFloorFaceIndex);
		}
	} else {
		// The character does not change position when it is turning
		direction = currentDirection;

		Math::Matrix3 turnRot;
		turnRot.buildAroundZ(_turnDirection == kTurnLeft ? -getAngularSpeed() : getAngularSpeed());
		turnRot.transformVector(&direction);
	}

	if (direction.getMagnitude() != 0.f) {
		_item3D->setDirection(computeAngleBetweenVectorsXYPlane(direction, Math::Vector3d(1.0, 0.0, 0.0)));
	}
}

float DirectWalk::getAngularSpeed() const {
	return _defaultTurnAngleSpeed * StarkGlobal->getMillisecondsPerGameloop();
}

float DirectWalk::computeDistancePerGameLoop() const {
	Resources::Anim *anim = _item->getAnim();
	if (!anim) {
		return 0.f;
	}

	return anim->getMovementSpeed() * StarkGlobal->getMillisecondsPerGameloop() / 1000.f;
}

void DirectWalk::changeItemAnim() {
	if (_ended) {
		_item->setAnimActivity(Resources::Anim::kActorActivityIdle);
	} else if (_turnDirection != kTurnNone) {
		_item->setAnimActivity(Resources::Anim::kActorActivityIdle);
	} else if (_running) {
		_item->setAnimActivity(Resources::Anim::kActorActivityRun);
	} else {
		_item->setAnimActivity(Resources::Anim::kActorActivityWalk);
	}
}

uint32 DirectWalk::getType() const {
	return kTypeDirectWalk;
}

void DirectWalk::saveLoad(ResourceSerializer *serializer) {
	serializer->syncAsFloat(_inputX);
	serializer->syncAsFloat(_inputY);
	serializer->syncAsUint32LE(_running);
}

} // End of namespace Stark
